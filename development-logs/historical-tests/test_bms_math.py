"""Compile the actual patched arithmetic functions on the build host."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class BmsMathTests(unittest.TestCase):
    def test_actual_c_arithmetic(self):
        source=(Path(__file__).resolve().parents[1]/'hardware/bms/mi4_bms_fixed.c').read_text()
        interpolation=source[source.index('static int column_capacity'):source.index('static int bms_lock_output_data')]
        calibration=source[source.index('static int bms_adc_uv'):source.index('static int column_capacity')]
        counter=source[source.index('\tquotient = div_s64(cc_raw, 982920000);'):source.index('\n\tdev_dbg(di->dev, "read coulomb counter')]
        harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <stdbool.h>
typedef uint32_t u32; typedef int8_t s8; typedef uint8_t u8; typedef int64_t s64;
#define __maybe_unused
#define TEMPERATURE_COLS 5
#define MAX_CAPACITY_ROWS 50
struct bms_device_info { int lo,hi; };
static int bms_adc_raw(struct bms_device_info *d,int n,int *v) { *v=n==9?d->lo:d->hi; return 0; }
static s64 div_s64(s64 a,int b) { return a/b; }
static int fixp_linear_interpolate(int x0,int y0,int x1,int y1,int x) { return y0+(s64)(x-x0)*(y1-y0)/(x1-x0); }
struct bms_ocv_lut { int rows; s8 temp_legend[5]; u8 capacity_legend[50]; u32 lut[50][5]; };
struct bms_fcc_lut { s8 temp_legend[5]; u32 lut[5]; };
'''+calibration+interpolation+'''
static s64 counter(s64 cc_raw) { s64 quotient,remainder,value,*cc_uah=&value;
'''+counter+'''return value; }
int main(void) {
 struct bms_device_info adc={31080,37455}; int uv;
 assert(bms_adc_uv(&adc,37899,&uv)==0 && uv>3880000 && uv<3890000);
 assert(bms_adc_uv(&adc,36000,&uv)==0 && uv>3300000 && uv<3330000);
 adc.hi=adc.lo; assert(bms_adc_uv(&adc,37899,&uv)==-ERANGE);
 struct bms_ocv_lut lut={.rows=3,.temp_legend={-10,0,25,50,65},.capacity_legend={100,50,0}};
 struct bms_fcc_lut fcc={.temp_legend={-10,0,25,50,65},.lut={3230000,3260000,3380000,3410000,3360000}};
 for(int i=0;i<3;i++) for(int j=0;j<5;j++) lut.lut[i][j]=4300000-i*650000;
 for(int t=-50;t<100;t++) {
   assert(interpolate_capacity(t,4500000,&lut)==100);
   assert(interpolate_capacity(t,2800000,&lut)==0);
   int c=interpolate_capacity(t,3800000,&lut); assert(c>=60 && c<=62);
   assert(interpolate_fcc(t,&fcc)>=3230000 && interpolate_fcc(t,&fcc)<=3410000);
 }
 assert(counter(1000000)==257 && counter(-1000000)==-257);
 assert(counter(982920000LL)==253183);
 assert(counter(9829200000000LL)==2531830000LL);
 puts("BMS_C_MATH_OK: ADC, invalid references, LUT bounds, signed/extended CC");
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            (path/'math.c').write_text(harness)
            subprocess.run(['cc','-fsanitize=undefined','-fno-sanitize-recover=all',str(path/'math.c'),'-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True)


if __name__=='__main__': unittest.main()
