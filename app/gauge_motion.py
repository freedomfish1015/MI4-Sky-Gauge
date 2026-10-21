"""Read-only, throttled dashboard adapter; no hardware work in rendering."""
import json
import collections
import math
from pathlib import Path
import time

STATE = Path('/run/obd-motion/state.json')
CONTROL = Path.home() / '.config/obd-gauge/motion-control.json'
DISPLAY_RANGE_G = 2.2
METER_BOUNDS = (180, 40, 280, 310)
CIRCLE_BOUNDS = (179, 39, 282, 282)
VALUE_BOUNDS = (273, 320, 78, 29)
PEAK_BOUNDS = ((291,62,58,29),(291,296,58,24),(184,172,54,27),(402,172,54,27))


def acceleration_available(imu):
    return bool(imu.get('ready') and
                (imu.get('measurement_mode') in ('accelerometer_raw','accelerometer_autocenter')
                 or imu.get('calibrated')))


def display_vector(x,y):
    scale = max(DISPLAY_RANGE_G,math.hypot(x,y))
    return x/scale,y/scale


def directional_contour(points, sectors=72):
    """Angle-ordered radial outline, NOT a convex hull. Keep measured valleys.

    Join observed sectors in angular order; do not insert spikes for small gaps
    between sectors. A wholly unobserved half-plane closes through the origin.
    Original G values remain untouched; only the display is clipped.
    """
    best = [(0.,0.) for _ in range(sectors)]
    for x,y in points:
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        index = int((math.atan2(y,x)+math.pi)/math.tau*sectors)%sectors
        old = best[index]
        if x*x+y*y > old[0]*old[0]+old[1]*old[1]:
            best[index] = (x,y)
    observed=[point for point in best if point!=(0.,0.)]
    if not observed:
        return []
    result=[]
    for i,point in enumerate(observed):
        result.append(display_vector(*point))
        following=observed[(i+1)%len(observed)]
        gap=(math.atan2(following[1],following[0])-math.atan2(point[1],point[0]))%math.tau
        if len(observed)==1 or gap>math.pi+1e-9:
            result.append((0.,0.))
    return result


def rounded_contour_segments(points, corner=6.):
    """Local quadratic fillets; controls stay within adjacent vertex bounds.

    Do not average radial maxima or use an overshooting global spline. The
    measurement contour remains unchanged; only its drawn corners are rounded.
    """
    vertices=[]
    for point in points:
        if not vertices or point!=vertices[-1]:
            vertices.append(point)
    if len(vertices)>1 and vertices[0]==vertices[-1]:
        vertices.pop()
    if len(vertices)<3:
        return []
    result=[]
    for i,p in enumerate(vertices):
        before,after=vertices[i-1],vertices[(i+1)%len(vertices)]
        a,b=math.dist(p,before),math.dist(p,after)
        cut=min(corner,.42*a,.42*b)
        entry=tuple(p[j]+(before[j]-p[j])*cut/a for j in (0,1)) if a else p
        exit=tuple(p[j]+(after[j]-p[j])*cut/b for j in (0,1)) if b else p
        result.append((entry,p,exit))
    return result


def motion_bounds(state, envelope=False):
    imu = state.get('imu',{})
    points = [state.get('_visual_point',imu.get('display_g',(0,0)))]
    points += [(x,y) for _stamp,x,y in state.get('trail',())]
    if envelope:
        points += list(state.get('_visual_envelope',imu.get('envelope_g',())))
    mapped = [(320+136*display_vector(x,y)[0],180+136*display_vector(x,y)[1]) for x,y in points]
    xs,ys = zip(*mapped)
    left,top = math.floor(min(xs)-8),math.floor(min(ys)-8)
    return (left,top,math.ceil(max(xs)+8)-left,math.ceil(max(ys)+8)-top)


def convex_hull(points):
    points = sorted(set(points))
    if len(points) < 3:
        return points
    def cross(o,a,b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    def half(sequence):
        result = []
        for point in sequence:
            while len(result) >= 2 and cross(result[-2],result[-1],point) <= 0:
                result.pop()
            result.append(point)
        return result
    return half(points)[:-1] + half(reversed(points))[:-1]


class MotionClient:
    def __init__(self):
        self.state = {}
        self.last = 0
        self.history = collections.deque(maxlen=100)
        self.sample_token = None
        self.visual_point = None
        self.visual_bins = [[0.0,0.0] for _ in range(72)]
        self.visual_at = time.monotonic()

    def smooth(self, state):
        now = time.monotonic()
        dt = max(0,min(.1,now-self.visual_at))
        self.visual_at = now
        imu = state.get('imu',{})
        if not acceleration_available(imu):
            self.visual_point = None
            self.visual_bins = [[0.0,0.0] for _ in range(72)]
            return False
        target = imu.get('display_g',(0,0))
        if imu.get('measurement_mode') in ('accelerometer_raw','accelerometer_autocenter'):
            self.visual_point = list(target)
            state['_visual_point'] = list(target)
            state['_visual_envelope'] = list(imu.get('envelope_g',()))
            return False  # Display the sensor daemon's output without extra lag.
        if self.visual_point is None:
            self.visual_point = list(target)
        alpha = 1-math.exp(-dt/.09)
        self.visual_point = [a+(b-a)*alpha for a,b in zip(self.visual_point,target)]
        targets = [[0.0,0.0] for _ in range(72)]
        for x,y in imu.get('envelope_g',()):
            index = int((math.atan2(y,x)+math.pi)/math.tau*72)%72
            targets[index] = [x,y]
        for i in range(72):
            self.visual_bins[i] = [a+(b-a)*alpha for a,b in zip(self.visual_bins[i],targets[i])]
        state['_visual_point'] = list(self.visual_point)
        state['_visual_envelope'] = list(self.visual_bins)
        return (math.hypot(*(a-b for a,b in zip(self.visual_point,target))) > .001 or
                any(math.hypot(*(a-b for a,b in zip(v,t)))>.002 for v,t in zip(self.visual_bins,targets)))

    def read(self):
        now = time.monotonic()
        if now - self.last < .1:
            return self.state
        self.last = now
        try:
            state = json.loads(STATE.read_text())
            self.state = state if now - state.get('updated', -100) < 2 else {}
        except (OSError, ValueError):
            self.state = {}
        imu = self.state.get('imu', {})
        if acceleration_available(imu):
            if self.sample_token != self.state.get('updated'):
                self.sample_token = self.state.get('updated')
                self.history.append((now, *imu.get('display_g', (0, 0))))
            while self.history and now - self.history[0][0] > 5.0:
                self.history.popleft()
            self.state['trail'] = list(self.history)
        else:
            self.history.clear()
        return self.state

    def command(self, **changes):
        try:
            current = json.loads(CONTROL.read_text())
        except (OSError, ValueError):
            current = {}
        current.update(changes)
        if 'zero' in changes:
            self.history.clear()
        CONTROL.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONTROL.with_suffix('.tmp')
        tmp.write_text(json.dumps(current))
        tmp.replace(CONTROL)

    def signature(self):
        state = self.read()
        animating = self.smooth(state)
        imu, gps = state.get('imu', {}), state.get('gps', {})
        point = imu.get('display_g', (0, 0))
        moving = any(math.hypot(x-point[0], y-point[1]) > .015
                     for _stamp,x,y in self.history)
        return (imu.get('ready', False), imu.get('calibrated', False),
                round(imu.get('plane_g', imu.get('total_g', 0)), 2), gps.get('fix', False),
                gps.get('satellites', 0), gps.get('status', ''),
                state.get('recording', False), state.get('points', 0),
                tuple(round(v, 2) for v in imu.get('display_g', (0, 0))),
                tuple(round(v, 2) for v in imu.get('peaks_g', (0, 0, 0, 0))),
                int(time.monotonic()*(60 if animating else 20)) if moving or animating else 0,
                tuple((round(x,2),round(y,2)) for x,y in imu.get('envelope_g',())))


def paint_meter(gauge, state):
    import cairo
    from gauge_sdl import Digits, RS
    cr = gauge.cr
    imu, gps = state.get('imu', {}), state.get('gps', {})
    cx, cy, radius = 320, 180, 136
    peak_positions = ((320,58),(320,290),(210,163),(430,163))
    if not hasattr(gauge, '_motion_art'):
        art = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(280*RS), int(310*RS))
        art.set_device_scale(RS, RS)
        ac = cairo.Context(art)
        ac.translate(-180,-40)
        ac.set_antialias(cairo.ANTIALIAS_BEST)
        ac.set_source_rgba(1, 1, 1, .92)
        ac.arc(cx, cy, radius + 3, 0, math.tau)
        ac.fill()
        ac.set_source_rgb(*gauge.theme['track'])
        ac.set_line_width(.9)
        for r in (radius/2, radius):
            ac.arc(cx, cy, r, 0, math.tau)
            ac.stroke()
        ac.move_to(cx-radius, cy)
        ac.line_to(cx+radius, cy)
        ac.move_to(cx, cy-radius)
        ac.line_to(cx, cy+radius)
        ac.stroke()
        for title, (x,y) in zip(('Y− MAX', 'Y+ MAX', 'X− MAX', 'X+ MAX'), peak_positions):
            gauge.text(ac, x, y, title, 8, gauge.theme['dim'], align='center')
        gauge.text(ac, 346,334,'G',10,gauge.theme['dim'],align='center')
        gauge.text(ac, 386,79,'2.2 G',7,gauge.theme['dim'],align='center')
        gauge._motion_art = art
        gauge._motion_digits, gauge._peak_digits = Digits(16), Digits(11)
    cr.set_source_surface(gauge._motion_art,180,40)
    cr.paint()
    valid = acceleration_available(imu)
    if valid:
        contour = directional_contour(state.get('_visual_envelope',imu.get('envelope_g',())))
        if any(x or y for x,y in contour):
            cr.save()
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            vertices=[(cx+radius*x,cy+radius*y) for x,y in contour]
            rounded=rounded_contour_segments(vertices)
            if rounded:
                cr.move_to(*rounded[0][0])
                for entry,p,exit in rounded:
                    cr.line_to(*entry)
                    # Quadratic Bezier converted to Cairo's cubic API.
                    a=tuple(entry[j]+2*(p[j]-entry[j])/3 for j in (0,1))
                    b=tuple(exit[j]+2*(p[j]-exit[j])/3 for j in (0,1))
                    cr.curve_to(*a,*b,*exit)
            else:
                for index,p in enumerate(vertices):
                    (cr.move_to if index==0 else cr.line_to)(*p)
            cr.close_path()
            cr.set_source_rgba(*gauge.theme['accent'], .22)
            cr.fill_preserve()
            cr.set_source_rgba(*gauge.theme['accent'], .78)
            cr.set_line_width(1.1)
            cr.stroke()
            cr.restore()
        trail = state.get('trail', [])
        now = time.monotonic()
        cr.save()
        cr.arc(cx,cy,radius,0,math.tau)
        cr.clip()
        for i,(previous,current) in enumerate(zip(trail,trail[1:])):
            age = now-current[0]
            if age > 5:
                continue
            freshness = max(0.0, 1-age/5)
            cr.set_source_rgba(*gauge.theme['accent'], .55*freshness*freshness)
            cr.set_line_width(.7 + 3.0*freshness)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            controls = (trail[max(0,i-1)],previous,current,trail[min(len(trail)-1,i+2)])
            p = [(cx+radius*display_vector(x,y)[0],cy+radius*display_vector(x,y)[1])
                 for _stamp,x,y in controls]
            cr.move_to(*p[1])
            cr.curve_to(p[1][0]+(p[2][0]-p[0][0])/6,p[1][1]+(p[2][1]-p[0][1])/6,
                        p[2][0]-(p[3][0]-p[1][0])/6,p[2][1]-(p[3][1]-p[1][1])/6,*p[2])
            cr.stroke()
        cr.restore()
        x,y = state.get('_visual_point',imu['display_g'])
        x,y = display_vector(x,y)
        cr.set_source_rgb(*gauge.theme['accent'])
        cr.arc(cx + radius*x, cy + radius*y, 5, 0, math.tau)
        cr.fill()
    visual = state.get('_visual_point',imu.get('display_g',(0,0)))
    gauge._motion_digits.draw(cr,313,334,
                              '%.2f' % math.hypot(*visual) if valid else '--',
                              gauge.theme['text'])
    peaks = imu.get('peaks_g', [0.0] * 4)
    for value, (x, y) in zip(peaks, peak_positions):
        gauge._peak_digits.draw(cr, x, y+17, '%.2f' % value if valid else '--',
                                gauge.theme['accent'])
    label = ('GPS 已定位' if gps.get('fix') else 'GPS 搜索中' if gps.get('session_started')
             else 'GPS 未就绪' if state else '传感器离线')
    if state.get('recording'):
        label += ' · REC'
    if cr.clip_extents()[3] >= 346:
        gauge.text(cr,cx,354,label,8,gauge.theme['dim'],align='center')
