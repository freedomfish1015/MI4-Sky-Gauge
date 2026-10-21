import csv
from datetime import datetime,timezone,timedelta
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from gauge_tracks import CsvRoute,TrackView,coordinate,projected
from gauge_settings import Config,TouchSettings


def rows(path,points):
    with path.open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['utc','latitude','longitude','accuracy_m'])
        for second,lat,lon,accuracy in points:
            stamp=datetime(2026,10,20,tzinfo=timezone.utc)+timedelta(seconds=second)
            writer.writerow([stamp.isoformat(),lat,lon,accuracy])


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)

    def test_only_complete_valid_points_and_no_gap_join(self):
        path=self.directory/'trip.csv'
        rows(path,[(0,30,120,5),(1,30.0001,120,5),(2,30.0002,120,999),
                   (3,30.0003,120,5),(20,30.002,120,5)])
        route=CsvRoute(path);route.read()
        self.assertEqual(route.count,4)
        self.assertEqual([p[4] for p in route.points],[True,False,True,True])
        self.assertAlmostEqual(route.metres,11.119,places=2)
        with path.open('a') as stream:stream.write('2026-10-20T00:00:21+00:00,30.0021,120,')
        route.read();self.assertEqual(route.count,4)
        with path.open('a') as stream:stream.write('5\n')
        route.read();self.assertEqual(route.count,5)
        self.assertFalse(route.points[-1][4])

    def test_jump_rejected_and_dateline_projection_local(self):
        path=self.directory/'trip.csv'
        rows(path,[(0,30,120,5),(1,40,130,5),(2,30.0001,120,5)])
        route=CsvRoute(path);route.read()
        self.assertEqual(route.count,2)
        self.assertTrue(route.points[-1][4])
        points=projected([(0,0,179.999,5,True),(1,0,-179.999,5,False)])
        self.assertLess(abs(points[1][0]),250)

    def test_display_memory_is_bounded_and_original_not_changed(self):
        path=self.directory/'trip.csv'
        rows(path,[(i,30+i*.000001,120,5) for i in range(14000)])
        before=path.stat().st_size
        route=CsvRoute(path)
        while True:
            route.read()
            if not route.loading:break
        self.assertEqual(route.count,14000)
        self.assertLessEqual(len(route.points),12000)
        self.assertEqual(route.points[-1][0]-route.points[0][0],13999)
        self.assertEqual(path.stat().st_size,before)

    def test_latest_nonempty_history_and_current_empty_record(self):
        rows(self.directory/'old.csv',[(0,30,120,5),(1,30.0001,120,5)])
        rows(self.directory/'new.csv',[])
        view=TrackView(self.directory)
        view.refresh()
        self.assertEqual(view.snapshot()['name'],'old.csv')
        view.motion=dict(recording=True,track='new')
        view.refresh()
        self.assertEqual(view.snapshot()['name'],'new.csv')
        self.assertEqual(view.snapshot()['count'],0)
        view.tap(320,20);view.refresh()
        self.assertEqual(view.snapshot()['name'],'old.csv')

    def test_bad_coordinates_do_not_become_zero(self):
        for lat in ('nan','inf','91','bad'):
            self.assertIsNone(coordinate(dict(utc='2026-10-20T00:00:00Z',latitude=lat,longitude='120',accuracy_m='5')))

    def test_gestures_do_not_replace_log_and_record_button(self):
        config=Config(self.directory/'config')
        controls=TouchSettings(config,Mock(),brightness=Mock(read=lambda:50))
        controls.motion=Mock(read=lambda:dict(recording=False))
        controls.track_view=TrackView(self.directory)
        controls.input('down',300,280,1);controls.input('up',300,90,1.3)
        self.assertEqual(controls.page,'route')
        controls.input('down',550,22,2);controls.input('up',550,22,2.1)
        controls.motion.command.assert_called_once_with(record=True)
        controls.input('down',300,90,3);controls.input('up',300,280,3.3)
        self.assertEqual(controls.page,'gauge')
        controls.input('down',300,90,4);controls.input('up',300,280,4.3)
        self.assertEqual(controls.page,'telemetry')

    def test_native_paint_and_restore(self):
        import gauge_sdl as g
        from gauge_tracks import paint
        source=SimpleNamespace(read=lambda:dict(rpm=2000,speed=30,oil=80,coolant=90,battery=13),
                               connection_status=lambda:'测试连接',configure=lambda *a:None)
        config=Config(self.directory/'config')
        controls=TouchSettings(config,source,brightness=Mock(read=lambda:50))
        controls.motion=Mock(read=lambda:{})
        gauge=g.Gauge(source,headless=True,controls=controls)
        rows(self.directory/'trip.csv',[(0,30,120,5),(1,30.0001,120,5)])
        view=TrackView(self.directory);view.refresh()
        paint(gauge,view,{})
        gauge.tracks=view
        controls.page='route'
        self.assertTrue(gauge.draw_interactive_frame())
        controls.page='gauge'
        self.assertTrue(gauge.draw_interactive_frame())
        view.close()


if __name__=='__main__':unittest.main()
