"""Offline route viewer. Read existing CSVs in a worker; never edit GPS logs."""
import csv
from datetime import datetime, timezone, timedelta
import math
from pathlib import Path
import threading
import time

TRACKS = Path('/var/lib/obd-motion/tracks')
EARTH = 6371000.0
LIMIT = 12000


def coordinate(row):
    try:
        lat, lon = float(row['latitude']), float(row['longitude'])
        accuracy = float(row['accuracy_m'])
        stamp = datetime.fromisoformat(row['utc'].replace('Z','+00:00'))
        if stamp.tzinfo is None:
            return None
        utc = stamp.timestamp()
        if (not all(math.isfinite(v) for v in (lat,lon,accuracy,utc)) or
                not -90 <= lat <= 90 or not -180 <= lon <= 180 or not 0 <= accuracy <= 100):
            return None
        return utc, lat, lon, accuracy
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


def distance(a,b):
    p1,p2 = math.radians(a[1]),math.radians(b[1])
    dp,dl = p2-p1,math.radians((b[2]-a[2]+180)%360-180)
    h = math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*EARTH*math.asin(math.sqrt(min(1,max(0,h))))


def projected(points):
    if not points:
        return []
    lat0,lon0 = points[0][1:3]
    factor = max(.000001,math.cos(math.radians(lat0)))
    return [(EARTH*math.radians((p[2]-lon0+180)%360-180)*factor,
             EARTH*math.radians(p[1]-lat0),p[4]) for p in points]


class CsvRoute:
    """Incremental complete-line reads; malformed/gap/jump points don't join."""
    def __init__(self,path):
        self.path=Path(path)
        self.offset=0
        self.remainder=b''
        self.header=None
        self.points=[]
        self.count=0
        self.metres=0.0
        self.previous=None
        self.broken=True
        self.loading=False
        self.token=None

    def read(self):
        stat=self.path.stat()
        if stat.st_size>64*1024*1024:
            raise ValueError('轨迹文件超过64MB读取上限')
        token=(stat.st_dev,stat.st_ino)
        if (self.token is not None and token!=self.token) or stat.st_size<self.offset:
            self.__init__(self.path)
        self.token=token
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            chunk=stream.read(256*1024)
        self.offset+=len(chunk)
        self.loading=self.offset<stat.st_size
        data=self.remainder+chunk
        lines=data.split(b'\n')
        self.remainder=lines.pop()
        if len(self.remainder)>16384:
            self.remainder=b''
            self.broken=True
        for raw in lines:
            if len(raw)>16384:
                self.broken=True
                continue
            try:
                fields=next(csv.reader([raw.decode('utf-8-sig').rstrip('\r')]))
            except (UnicodeError,csv.Error,StopIteration):
                self.broken=True
                continue
            if self.header is None:
                self.header=fields
                if not {'utc','latitude','longitude','accuracy_m'}.issubset(fields):
                    raise ValueError('不支持的轨迹CSV格式')
                continue
            point=coordinate(dict(zip(self.header,fields)))
            if point is None:
                self.broken=True
                continue
            utc,lat,lon,accuracy=point
            if self.previous:
                elapsed=utc-self.previous[0]
                if elapsed<=0:
                    continue
                gap=distance(self.previous,point)
                if elapsed<=5 and gap>max(120*elapsed,100+accuracy+self.previous[3]):
                    self.broken=True
                    continue  # isolated GPS jump; don't distort route bounds
                split=self.broken or elapsed>5
                if not split:
                    self.metres+=gap
            else:
                split=True
            self.points.append((utc,lat,lon,accuracy,split))
            self.count+=1
            self.previous=point
            self.broken=False
            if len(self.points)>LIMIT:
                # Bounded display simplification; original CSV is never touched.
                old=self.points
                thin=[old[0]]
                for i in range(1,len(old),2):
                    block=old[i:i+2]
                    chosen=block[-1]
                    thin.append((*chosen[:4],any(p[4] for p in block)))
                self.points=thin
        return bool(chunk)


class TrackView:
    def __init__(self,directory=TRACKS):
        self.directory=Path(directory)
        self.lock=threading.Lock()
        self.wake=threading.Event()
        self.worker=None
        self.closed=False
        self.follow=True
        self.selected=''
        self.files=[]
        self.motion={}
        self.zoom=1.0
        self.last_request=-100
        self.revision=0
        self.result=dict(points=(),count=0,metres=0,name='',loading=False,error='')
        self.reader=None

    def tick(self,motion,now):
        if now-self.last_request<1:
            return
        self.last_request=now
        with self.lock:
            self.motion=dict(recording=motion.get('recording',False),track=motion.get('track',''),
                             gps=dict(motion.get('gps',{})))
        if self.worker is None:
            self.worker=threading.Thread(target=self._worker,name='gps-route-reader',daemon=True)
            self.worker.start()
        self.wake.set()

    def _worker(self):
        while True:
            self.wake.wait()
            self.wake.clear()
            if self.closed:
                return
            try:
                self.refresh()
            except (OSError,ValueError) as exc:
                with self.lock:
                    self.result=dict(self.result,error=str(exc)[:80])
                    self.revision+=1

    def refresh(self):
        # All filesystem work is off the render thread.
        base=self.directory.resolve()
        found=[]
        for path in self.directory.glob('*.csv'):
            if path.resolve().parent==base and path.is_file():
                found.append(path)
        found=sorted(found,key=lambda p:p.stat().st_mtime_ns,reverse=True)[:200]
        with self.lock:
            motion=dict(self.motion)
            selected,follow=self.selected,self.follow
        active=motion.get('track','')+'.csv'
        files=[]
        for path in found:
            with path.open('rb') as stream:
                stream.readline(16384)
                nonempty=bool(stream.readline(16384).strip())
            if nonempty or (motion.get('recording') and path.name==active):
                files.append(path.name)
        if follow and motion.get('recording') and active in files:
            selected=active
        elif selected not in files:
            selected=files[0] if files else ''
        result=dict(points=(),count=0,metres=0,name=selected,loading=False,error='')
        if selected:
            path=self.directory/selected
            if self.reader is None or self.reader.path!=path:
                self.reader=CsvRoute(path)
            self.reader.read()
            result.update(points=tuple(self.reader.points),count=self.reader.count,
                          metres=self.reader.metres,loading=self.reader.loading)
        with self.lock:
            # A tap that arrived during IO wins; next refresh loads that choice.
            if self.selected==self.result['name'] or self.selected==selected or not self.selected:
                self.selected=selected
                self.files=files
                self.result=result
                self.revision+=1
            else:
                self.files=files
                self.wake.set()

    def snapshot(self):
        with self.lock:
            return dict(self.result,zoom=self.zoom,files=tuple(self.files),motion=dict(self.motion))

    def tap(self,x,y):
        with self.lock:
            if 6<=y<=38 and 292<=x<=476 and self.files:
                index=self.files.index(self.selected) if self.selected in self.files else 0
                # Most recent first: older on left, newer on right.
                index=max(0,min(len(self.files)-1,index+(1 if x<384 else -1)))
                self.selected=self.files[index]
                self.follow=False
                self.zoom=1
                self.wake.set()
            elif 570<=x<=618:
                if 70<=y<=104:self.zoom=min(16,self.zoom*1.5)
                elif 112<=y<=146:self.zoom=max(1,self.zoom/1.5)
                elif 154<=y<=188:
                    self.zoom=1
                elif 196<=y<=230:
                    self.follow=True
                    self.selected=''
                    self.zoom=1
                    self.wake.set()
            self.revision+=1

    def close(self):
        self.closed=True
        self.wake.set()
        if self.worker:self.worker.join(timeout=1)


def paint(gauge,view,motion,message=''):
    cr=gauge.cr
    cr.save();cr.identity_matrix()
    cr.set_source_rgb(*gauge.theme['background']);cr.paint()
    gauge.apply_layout(cr)
    foreground,dim,accent=(gauge.theme[key] for key in ('text','dim','accent'))
    state=view.snapshot()
    def text(x,y,label,size=11,color=None,align='left'):
        gauge.text(cr,x,y,str(label),size,color or foreground,align=align)
    def button(x,y,w,h,label):
        gauge.rounded_card(cr,x,y,w,h,6)
        text(x+w/2,y+h/2,label,11,align='center')
    button(12,6,82,32,'‹ 仪表')
    text(111,22,'GPS / 行驶轨迹',15)
    button(292,6,88,32,'‹ 上一条')
    button(388,6,88,32,'下一条 ›')
    button(500,6,128,32,'停止记录' if motion.get('recording') else '开始记录')
    name=state['name']
    date='暂无轨迹 · 点击开始记录'
    if name:
        try:
            stamp=datetime.strptime(name[:16],'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            date=stamp.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            date=name[:34]
    if name in state['files']:
        date+='  %d/%d'%(state['files'].index(name)+1,len(state['files']))
    text(20,49,date,10,dim)
    gps=motion.get('gps',{})
    text(620,49,'已定位' if gps.get('fix') else '未定位 · 历史路线仍可查看',10,
         accent if gps.get('fix') else dim,'right')
    gauge.rounded_card(cr,16,62,608,254,9)
    cr.save();cr.rectangle(20,66,546,246);cr.clip()
    cr.set_source_rgba(*dim,.12);cr.set_line_width(.5)
    for x in range(28,564,40):cr.move_to(x,66);cr.line_to(x,312)
    for y in range(72,313,40):cr.move_to(20,y);cr.line_to(566,y)
    cr.stroke()
    points=projected(state['points'])
    if points:
        xs,ys=[p[0] for p in points],[p[1] for p in points]
        cx,cy=(min(xs)+max(xs))/2,(min(ys)+max(ys))/2
        scale=min(486/max(60,max(xs)-min(xs)),198/max(60,max(ys)-min(ys)))*state['zoom']
        mapped=[(293+(x-cx)*scale,187-(y-cy)*scale,split) for x,y,split in points]
        cr.set_source_rgb(*accent);cr.set_line_width(2.2);cr.set_line_join(1);cr.set_line_cap(1)
        for i,(x,y,split) in enumerate(mapped):
            if i==0 or split:cr.move_to(x,y)
            else:cr.line_to(x,y)
        cr.stroke()
        overlap=math.hypot(mapped[0][0]-mapped[-1][0],mapped[0][1]-mapped[-1][1])<9
        for point,color,radius in ((mapped[0],(.16,.62,.38),6 if overlap else 4),
                                   (mapped[-1],(.84,.23,.32),3.5 if overlap else 4)):
            cr.set_source_rgb(*color);cr.arc(point[0],point[1],radius,0,math.tau);cr.fill()
        bar_m=10**math.floor(math.log10(90/scale))
        for value in (bar_m*5,bar_m*2,bar_m):
            if value*scale<=100:bar_m=value;break
        cr.set_source_rgb(*foreground);cr.set_line_width(1.3)
        cr.move_to(32,295);cr.line_to(32+bar_m*scale,295);cr.stroke()
        text(32,282,('%.1f km'%(bar_m/1000) if bar_m>=1000 else '%g m'%bar_m),9,dim)
    else:
        text(293,170,'暂无有效轨迹点',20,dim,'center')
        text(293,200,'开始记录后，获得有效定位才会绘制路线',12,dim,'center')
    text(32,82,'N ↑',10,dim)
    cr.restore()
    for y,label in ((70,'＋'),(112,'－'),(154,'全览'),(196,'最新')):
        button(570,y,48,34,label)
    metres=state['metres']
    length=('%.2f km'%(metres/1000)) if metres>=1000 else '%.0f m'%metres
    text(20,337,'%s · %d 点 · %s'%('记录中' if motion.get('recording') else '已停止记录',state['count'],length),11)
    status=(message or ('存储空间不足，无法继续记录' if motion.get('storage_full') else '') or
            state['error'] or ('正在读取…' if state['loading'] else '绿起点 / 红终点 · 下滑返回'))
    text(620,337,status,10,dim,'right')
    cr.restore()
    gauge.surface.flush()
