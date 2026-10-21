"""Rei light instrument layout. Presentation only; no sensor/OBD/power changes.

Explicit presentation plug-in for the existing dirty-region renderer. Static
art stays cached, primary values use cached glyphs, and all four configurable
windows retain their original bindings and warning thresholds.
"""
import math
import sys
import time
import unicodedata

CARD_W, CARD_H = 154, 90
SPEED_CX, RPM_CX = 88, 552
READOUT_Y = 177
RAIL_TOP, RAIL_BOTTOM = 116, 244
RAIL_WIDTH = 16
SPEED_RAIL, RPM_RAIL = 175, 465


def apply_home_design(Gauge):
    if getattr(Gauge,'_home_design',False):
        return
    g=sys.modules[Gauge.__module__]
    g.BG=(.958,.976,.987)
    g.WHITE=(.075,.155,.223)
    g.DIM=(.37,.47,.55)
    g.BLUE=(.19,.40,.60)
    g.CYAN=(.24,.65,.76)
    g.TRACK=(.84,.89,.92)
    g.CARD_EDGE=(.80,.86,.90)
    g.CARD_W,g.CARD_H=CARD_W,CARD_H
    g.CARD_X,g.CARD_Y=(14,472),(18,252)
    g.CARDS=[(g.CARD_X[0],18,'电压','battery','%.1f','V'),
             (g.CARD_X[1],18,'水温','coolant','%.0f','°C'),
             (g.CARD_X[0],252,'油温','oil','%.0f','°C'),
             (g.CARD_X[1],252,'时速','speed','%.0f','km/h')]
    Gauge.theme=dict(background=g.BG,text=g.WHITE,dim=g.DIM,accent=g.BLUE,track=g.TRACK)

    def capsule(cr,x,y,w,h,r):
        cr.new_path()
        cr.arc(x+w-r,y+r,r,-math.pi/2,0)
        cr.arc(x+w-r,y+h-r,r,0,math.pi/2)
        cr.arc(x+r,y+h-r,r,math.pi/2,math.pi)
        cr.arc(x+r,y+r,r,math.pi,math.pi*1.5)
        cr.close_path()

    def label_fit(label,unit):
        budget=CARD_W-33-len(unit)*5.
        def width(s):
            return sum(10.5 if unicodedata.east_asian_width(c) in 'WF' else 5.8 for c in s)
        while len(label)>2 and width(label)>budget:
            label=label[:-2]+'…'
        return label

    def panel(self,cr,x,y,w,h):
        # Subtle, cached shadow: no blur or per-frame decoration rasterisation.
        capsule(cr,x,y+1.5,w,h,10)
        cr.set_source_rgba(.31,.47,.60,.055)
        cr.fill()
        capsule(cr,x,y,w,h,10)
        cr.set_source_rgb(1,1,1)
        cr.fill_preserve()
        cr.set_source_rgb(*g.CARD_EDGE)
        cr.set_line_width(.65)
        cr.stroke()
        cr.set_source_rgba(*g.BLUE,.65)
        capsule(cr,x+12,y+12,2.5,9,1.2)
        cr.fill()

    def rail_background(self,cr,x,maximum,redline,left):
        cr.set_line_cap(g.cairo.LINE_CAP_ROUND)
        cr.set_line_width(RAIL_WIDTH)
        cr.set_source_rgb(*g.TRACK)
        cr.move_to(x,RAIL_BOTTOM)
        cr.line_to(x,RAIL_TOP)
        cr.stroke()
        if redline is not None:
            threshold=RAIL_BOTTOM-(RAIL_BOTTOM-RAIL_TOP)*redline/maximum
            cr.set_source_rgb(.91,.79,.81)
            cr.move_to(x,threshold)
            cr.line_to(x,RAIL_TOP)
            cr.stroke()
        cr.set_line_width(.55)
        direction=-1 if left else 1
        for i in range(9):
            y=RAIL_BOTTOM-(RAIL_BOTTOM-RAIL_TOP)*i/8
            cr.set_source_rgba(*g.DIM,.42)
            cr.move_to(x+direction*(RAIL_WIDTH/2+3),y)
            cr.line_to(x+direction*(RAIL_WIDTH/2+(7 if i%2==0 else 5)),y)
            cr.stroke()

    def build_static(self):
        cr=g.cairo.Context(self.static)
        cr.set_source_rgb(*g.BG)
        cr.paint()
        self.apply_layout(cr)
        wash=g.cairo.RadialGradient(320,160,10,320,180,350)
        wash.add_color_stop_rgb(0,1,1,1)
        wash.add_color_stop_rgb(1,*g.BG)
        cr.set_source(wash)
        cr.paint()
        # A quiet, thin hexagonal signature replaces the heavy bezel.
        cr.save()
        capsule(cr,181,30,278,301,24)
        cr.set_source_rgba(1,1,1,.72)
        cr.fill()
        cr.save()
        cr.arc(320,180,133,0,math.tau)
        cr.clip()
        self.draw_rei_portrait(cr,199,52,242,242,opacity=.10)
        cr.restore()
        cr.restore()
        cr.set_line_width(.6)
        cr.set_source_rgba(*g.CARD_EDGE,.55)
        self.hex_path(cr,164)
        cr.stroke()
        rail_background(self,cr,SPEED_RAIL,g.SPEED_MAX,None,True)
        rail_background(self,cr,RPM_RAIL,g.RPM_MAX,g.RPM_REDLINE,False)
        for cx,label,unit in ((SPEED_CX,'车速','km/h'),(RPM_CX,'转速','RPM')):
            self.text(cr,cx,132,label,12,g.DIM)
            self.text(cr,cx,213,unit,10,g.DIM)
        # Small, functional colour keys distinguish the independent instruments.
        for cx,color in ((SPEED_CX,g.CYAN),(RPM_CX,g.BLUE)):
            capsule(cr,cx-10,230,20,2,1)
            cr.set_source_rgba(*color,.75)
            cr.fill()
        for x,y,label,key,fmt,unit in self.cards:
            panel(self,cr,x,y,CARD_W,CARD_H)
            self.text(cr,x+21,y+17,label_fit(label,unit),10.5,g.DIM,align='left')
            self.text(cr,x+CARD_W-12,y+17,unit,9,g.DIM,align='right')
        self.static.flush()

    def rail(self,cr,x,ratio,redline):
        ratio=max(0.,min(1.,ratio))
        if ratio<1e-7:
            return
        height=RAIL_BOTTOM-RAIL_TOP
        grad=g.cairo.LinearGradient(0,RAIL_BOTTOM,0,RAIL_TOP)
        grad.add_color_stop_rgb(0,*g.CYAN)
        grad.add_color_stop_rgb(1,*g.BLUE)
        cr.save()
        cr.set_line_cap(g.cairo.LINE_CAP_ROUND)
        cr.set_line_width(RAIL_WIDTH)
        cr.set_source(grad)
        cr.move_to(x,RAIL_BOTTOM)
        cr.line_to(x,RAIL_BOTTOM-height*(ratio if redline is None else min(ratio,redline)))
        cr.stroke()
        if redline is not None and ratio>redline:
            cr.set_source_rgb(*g.RED)
            cr.move_to(x,RAIL_BOTTOM-height*redline)
            cr.line_to(x,RAIL_BOTTOM-height*ratio)
            cr.stroke()
        cr.restore()

    def draw_progress(self,cr,a_from,a_to):
        rail(self,cr,RPM_RAIL,(70-math.degrees(a_to))/140,g.RPM_REDLINE/g.RPM_MAX)

    def draw_speed_progress(self,cr,a_from,a_to):
        rail(self,cr,SPEED_RAIL,(math.degrees(a_to)-110)/140,None)

    def card_value_box(self,index):
        x,y,*_=self.cards[index]
        return (x+8,y+34,CARD_W-16,47)

    def draw_card_value(self,cr,index,values):
        x,y,label,key,fmt,unit=self.cards[index]
        value=values.get(key,math.nan)
        self.card_digits.draw(cr,x+CARD_W/2,y+59,self.value_label(fmt,value),g.value_color(key,value))

    def rpm_value_box(self):
        return (482,150,140,54)

    def speed_value_box(self):
        return (18,145,140,62)

    def draw_rpm(self,cr,rpm):
        color=g.RED if math.isfinite(rpm) and rpm>=g.RPM_REDLINE else g.WHITE
        self.big_digits.draw(cr,RPM_CX,READOUT_Y,self.rpm_label(rpm),color)

    def draw_speed(self,cr,speed):
        self.speed_digits.draw(cr,SPEED_CX,READOUT_Y,self.value_label('%.0f',speed),g.WHITE)

    def arc_box(self,a0,a1):
        return (455,106,173,148)

    def speed_arc_box(self,a0,a1):
        return (12,106,173,148)

    original=Gauge.draw_frame
    def draw_frame(self,values,full=False,upload=True):
        # The old centre intentionally hid speed/RPM digits, so its core only
        # dirties arcs. Explicitly cover digit changes even when the arc clamps
        # (above maximum), or when zero changes to missing/NaN.
        before_rpm,before_speed=self.shown_rpm,self.shown_speed
        regions=original(self,values,full=full,upload=False)
        extra=[]
        def covered(box):
            x,y,w,h=box
            return any(a<=x and b<=y and a+c>=x+w and b+d>=y+h for (a,b,c,d),_m in regions)
        if before_rpm!=self.shown_rpm and not covered(rpm_value_box(self)):
            extra.append((rpm_value_box(self),g.REGION_RPM))
        if before_speed!=self.shown_speed and not covered(speed_value_box(self)):
            extra.append((speed_value_box(self),g.REGION_SPEED))
        if extra:
            start=time.perf_counter()
            extra=self.merge_regions(extra)
            self.paint(values,extra,values['rpm'])
            self.surface.flush()
            self.prof_paint+=time.perf_counter()-start
            regions=self.merge_regions(regions+extra)
        if upload:self.upload(regions)
        return regions

    for method in (build_static,draw_progress,draw_speed_progress,card_value_box,
                   draw_card_value,rpm_value_box,speed_value_box,draw_rpm,draw_speed,
                   arc_box,speed_arc_box,draw_frame):
        setattr(Gauge,method.__name__,method)
    Gauge._home_design=True
