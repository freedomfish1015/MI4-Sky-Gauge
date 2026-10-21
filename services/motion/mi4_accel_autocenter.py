"""Accelerometer-only, auto-centering dynamic G (not sustained vehicle G).

At 50 Hz, subtract an exponential low-pass baseline (tau=0.7 s), then apply
a continuous 0.025 G per-axis deadband. First sample establishes baseline
immediately, with no stationary/calibration wait. No gyroscope or integration.
"""
import math

G = 9.80665


class AutoCenter:
    def __init__(self, tau=.7, deadzone=.025):
        if not math.isfinite(tau) or tau <= 0 or not math.isfinite(deadzone) or deadzone < 0:
            raise ValueError('invalid auto-center parameters')
        self.tau, self.deadzone = tau, deadzone
        self.reset()

    def reset(self):
        self.baseline = None
        self.dynamic = None

    def update(self, accel_ms2, dt=.02):
        if len(accel_ms2) != 3 or not all(math.isfinite(v) for v in accel_ms2):
            raise ValueError('invalid accelerometer vector')
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('invalid sample interval')
        raw = [v/G for v in accel_ms2]
        if self.baseline is None:
            self.baseline = raw
            self.dynamic = [0.,0.,0.]
            return list(self.dynamic)
        alpha = -math.expm1(-dt/self.tau)
        self.baseline = [b+alpha*(r-b) for b,r in zip(self.baseline,raw)]
        self.dynamic = [math.copysign(max(0.,abs(r-b)-self.deadzone),r-b)
                        for r,b in zip(raw,self.baseline)]
        return list(self.dynamic)
