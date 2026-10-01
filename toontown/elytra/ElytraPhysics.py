"""Pure-math Elytra-style flight model (no Panda3D dependency so it can be unit-simulated).

Velocity is (vx, vy, vz) in world units/s, Z up.  The look direction is given by a
heading (degrees, Panda convention: 0 = +Y, positive turns left) and a pitch
(degrees, positive = looking up).  The model is energy based: gravity always acts
but is partly turned into forward speed when falling; pulling up trades forward
speed for climb; horizontal velocity steers toward the look direction; drag bleeds
energy away.
"""
import math
from . import ElytraConstants as C


def lookVector(heading, pitch):
    h = math.radians(heading)
    p = math.radians(pitch)
    cp = math.cos(p)
    return (-math.sin(h) * cp, math.cos(h) * cp, math.sin(p))


def stepFlight(vel, heading, pitch, dt, boostTime=0.0):
    """Advance velocity by dt seconds. Returns the new (vx, vy, vz)."""
    vx, vy, vz = vel
    dt = max(C.MIN_DT, min(C.MAX_DT, dt))
    h = math.radians(heading)
    lhx, lhy = -math.sin(h), math.cos(h)
    p = math.radians(pitch)
    cos2 = math.cos(p) ** 2
    hs = math.hypot(vx, vy)

    # gravity always applies, reduced (not removed) by the wings when facing level
    vz -= C.GRAVITY * (1.0 - C.LIFT_FACTOR * cos2) * dt

    # falling converts descent into forward speed and a little lift
    if vz < 0.0:
        conv = -vz * C.FALL_TO_FORWARD * cos2 * dt
        vz += conv
        vx += lhx * conv
        vy += lhy * conv

    # pulling up converts forward speed into climb
    if p > 0.0 and hs > 0.0:
        conv = hs * math.sin(p) * C.PULL_UP * dt
        vz += conv * C.PULL_UP_CLIMB_GAIN
        vx -= lhx * conv
        vy -= lhy * conv

    # gradually steer horizontal velocity toward the look heading (no snapping)
    hs = math.hypot(vx, vy)
    k = 1.0 - math.exp(-C.STEERING * dt)
    vx += (lhx * hs - vx) * k
    vy += (lhy * hs - vy) * k

    # firework burn: accelerate along the full look vector, never reducing speed already
    # carried in that direction
    if boostTime > 0.0:
        lx, ly, lz = lookVector(heading, pitch)
        along = vx * lx + vy * ly + vz * lz
        if along < C.BOOST_TARGET_SPEED:
            add = min(C.BOOST_TARGET_SPEED - along, C.BOOST_ACCEL * dt)
            vx += lx * add
            vy += ly * add
            vz += lz * add

    # drag
    dh = math.exp(-C.DRAG_H * dt)
    vx *= dh
    vy *= dh
    vz *= math.exp(-C.DRAG_V * dt)

    sp = math.sqrt(vx * vx + vy * vy + vz * vz)
    if sp > C.MAX_SPEED:
        s = C.MAX_SPEED / sp
        vx, vy, vz = vx * s, vy * s, vz * s
    return (vx, vy, vz)
