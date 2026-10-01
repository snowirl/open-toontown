"""Tunable constants for the Airplane Wings (Elytra-style) glide feature.

Units are Toontown world units (feet-ish) and seconds.  Walking is ~20 u/s.
"""
from panda3d.core import Point3

# ---- Assets (all pre-existing resources) ----
WINGS_BACKPACK_IDX = 17  # ToonDNA.BackpackStyles['bap1'] -> BackpackModels[17] (tt_m_chr_avt_acc_pac_airplane)
WINGS_STYLE = (WINGS_BACKPACK_IDX, 0, 0)
TNT_MODEL = 'phase_5/models/props/tnt-mod'
TNT_TIP_JOINT = 'joint_attachEmitter'
SND_TNT_LIGHT = 'phase_5/audio/sfx/TL_dynamite.ogg'
SND_LAUNCH = 'phase_13/audio/sfx/rocket_launch.ogg'
SND_POP = 'phase_4/audio/sfx/firework_explosion_01.ogg'
PTF_FIRE = 'tt_p_efx_rocketLaunchFire.ptf'
PTF_SMOKE = 'tt_p_efx_rocketLaunchSmoke.ptf'
PTF_SPARKS = 'tnt.ptf'
TEX_FIRE = 'phase_4/models/props/tt_m_efx_fireball'
TEX_SMOKE = 'phase_4/models/props/tt_m_efx_smoke'

# ---- Pickup (Toontown Central) ----
PICKUP_TTC_POS = Point3(-48, -17, 1.3)   # in front of the spawn (-60,-8), shifted away from the gazebo; z is re-snapped to the ground
PICKUP_RADIUS = 5.0
PICKUP_SCALE = 0.5
PICKUP_HOVER_HEIGHT = 2.5

# ---- Inputs ----
GLIDE_ACTIVATE_EVENT = 'control'        # the normal jump key, pressed while airborne
BOOST_KEYS = ('mouse1', 'mouse3')        # firework boost: left or right click (letter keys open chat)
MIN_AIRBORNE_TIME = 0.3                 # debounce after a glide ends before another may start
MIN_AIRBORNE_HEIGHT = 1.0               # units above ground

# ---- Mouse look ----
MOUSE_SENSITIVITY = 0.12                # degrees of rotation per pixel
MOUSE_SMOOTHING = 0.0                   # 0 = raw; otherwise low-pass time constant (s)
PITCH_LIMIT = 85.0                      # degrees
CAMERA_SMOOTH_TIME = 0.04               # seconds; view smoothing (camera only, flight uses smoothed view)
CAMERA_DIST = 15.0
CAMERA_UP = 2.0
CAMERA_BLEND_IN = 0.45
CAMERA_BLEND_OUT = 0.5

# ---- Physics ----
GRAVITY = 40.0
LIFT_FACTOR = 0.80              # fraction of gravity cancelled when looking level (cos^2 pitch scaled)
FALL_TO_FORWARD = 2.0           # rate at which downward speed converts into forward speed + lift
PULL_UP = 1.0                   # rate at which forward speed converts into climb when looking up
PULL_UP_CLIMB_GAIN = 3.2
STEERING = 2.0                  # 1/s, how quickly horizontal velocity aligns with the look direction
DRAG_H = 0.20                   # 1/s
DRAG_V = 0.35                   # 1/s
START_MIN_SPEED = 12.0          # forward speed given on glide start if slower
MAX_SPEED = 90.0                # safe maximum speed
MIN_DT = 1.0 / 240.0
MAX_DT = 1.0 / 20.0

# ---- Firework boost ----
BOOST_DURATION = 0.9
BOOST_ACCEL = 140.0             # u/s^2 applied along the look direction while burning
BOOST_TARGET_SPEED = 62.0       # burn stops adding speed along look past this (never slows you)
BOOST_COOLDOWN = 0.35
TNT_IN_HAND_TIME = 0.55
TRAIL_DURATION = 1.4            # seconds the emitters live before cleanup

# ---- Body pose ----
BODY_PITCH_RESPONSE = 8.0       # 1/s
BODY_YAW_RESPONSE = 10.0
BODY_BANK_RESPONSE = 5.0
BANK_PER_YAW_RATE = 0.35        # degrees of roll per degree/s of yaw rate
BANK_MAX = 40.0
GLIDE_ANIM_STATE = 'Glide'

# ---- Network ----
NET_SEND_INTERVAL = 0.1
EQUIP_REFRESH_INTERVAL = 4.0
