"""Minecraft-Elytra-style glide for the local Toon, powered by the Airplane Wings accessory.

Design:
  * The existing GravityWalker keeps its collision solids (wall pusher + floor lifter) alive,
    but its movement task is paused while gliding and its lifter gravity is zeroed, so this
    controller owns the Toon's motion.  Everything is restored when the glide ends.
  * The mouse (recentred each frame, cursor hidden and confined) drives a yaw/pitch "view";
    the view is also the camera orientation and the Elytra look vector.  Velocity is never
    set from the look vector directly - ElytraPhysics steers it toward it.
  * Motion is swept with collision segments against the level geometry so fast dives cannot
    tunnel through floors and walls.
"""
import math
from panda3d.core import (Vec3, Point3, Quat, WindowProperties, CollisionSegment, CollisionNode,
                          CollisionHandlerQueue, CollisionTraverser, BitMask32, NodePath)
from direct.showbase.DirectObject import DirectObject
from direct.task import Task
from direct.directnotify import DirectNotifyGlobal
from otp.otpbase import OTPGlobals
from . import ElytraConstants as C
from . import ElytraPhysics
from . import ElytraPose
from .ElytraEffects import ElytraEffects
from .ElytraRemote import FLAG_EQUIPPED, FLAG_GLIDING


def _angleDiff(target, current):
    return (target - current + 180.0) % 360.0 - 180.0


def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _nlerp(q0, q1, s):
    sign = 1.0 if (q0.getR() * q1.getR() + q0.getI() * q1.getI() + q0.getJ() * q1.getJ() + q0.getK() * q1.getK()) >= 0 else -1.0
    q = Quat(q0.getR() * (1 - s) + sign * q1.getR() * s,
             q0.getI() * (1 - s) + sign * q1.getI() * s,
             q0.getJ() * (1 - s) + sign * q1.getJ() * s,
             q0.getK() * (1 - s) + sign * q1.getK() * s)
    q.normalize()
    return q


class ElytraFlightController(DirectObject):
    notify = DirectNotifyGlobal.directNotify.newCategory('ElytraFlightController')

    def __init__(self, avatar):
        self.avatar = avatar
        self.hasWings = False
        self.gliding = False
        self.effects = ElytraEffects(avatar)
        self.updateTask = 'elytraGlideUpdate-%d' % id(self)
        self.refreshTask = 'elytraEquipRefresh-%d' % id(self)
        self.camReturnTask = 'elytraCameraReturn-%d' % id(self)
        self.lastStopTime = -10.0
        self.lastBoostTime = -10.0
        self.boostTime = 0.0
        self.vel = Vec3(0, 0, 0)
        # collision sweep helpers (created lazily)
        self._segNode = None
        self._segNP = None
        self._segQueue = None
        self._segTrav = None
        self._geom = None
        self._resetGlideState()

    # ------------------------------------------------------------------ equip
    def equipWings(self, announce=False):
        av = self.avatar
        self.hasWings = True
        av.setBackpack(*C.WINGS_STYLE)
        self.accept(C.GLIDE_ACTIVATE_EVENT, self._onActivateKey)
        for key in C.BOOST_KEYS:
            self.accept(key, self._onBoostKey)
        self._sendState(force=True)
        taskMgr.remove(self.refreshTask)
        taskMgr.doMethodLater(C.EQUIP_REFRESH_INTERVAL, self._refresh, self.refreshTask)
        if announce:
            av.setSystemMessage(0, 'You picked up the Airplane Wings! Jump, then press CTRL again in the air to glide. '
                                   'Steer with the mouse and click the mouse for a firework boost.')

    def _refresh(self, task):
        if not self.gliding:
            self._sendState(force=True)
        return task.again

    # ---------------------------------------------------------------- activation
    def canStartGlide(self):
        av = self.avatar
        if not self.hasWings or self.gliding or av.isEmpty():
            return False
        if not getattr(av, 'avatarControlsEnabled', 0):
            return False
        controls = av.controlManager
        if controls.currentControlsName != 'walk' or av.physControls is not controls.currentControls:
            return False
        lifter = av.physControls.lifter
        if lifter.isOnGround() or lifter.getAirborneHeight() < C.MIN_AIRBORNE_HEIGHT:
            return False
        if globalClock.getFrameTime() - self.lastStopTime < C.MIN_AIRBORNE_TIME:
            return False
        if av.hp <= 0 or av.sleepFlag:
            return False
        return True

    def _typing(self):
        try:
            name = self.avatar.chatMgr.fsm.getCurrentState().getName()
        except Exception:
            return False
        return name in ('normalChat', 'whisperChat', 'whisperChatPlayer')

    def _onActivateKey(self):
        if self._typing():
            return
        now = globalClock.getFrameTime()
        if self.gliding:
            if now - self.glideStartTime > 0.35:
                self.stopGlide(reason='cancel')
            return
        if self.canStartGlide():
            self.startGlide()

    def _onBoostKey(self):
        if self.gliding and not self._typing():
            self.boost()

    # ------------------------------------------------------------------ glide
    def _resetGlideState(self):
        self.glideStartTime = 0.0
        self.viewYaw = 0.0
        self.viewPitch = 0.0
        self.rawYaw = 0.0
        self.rawPitch = 0.0
        self.bodyYaw = 0.0
        self.bodyPitch = 0.0
        self.bodyBank = 0.0
        self.yawRate = 0.0
        self.camBlendT = 0.0
        self.camStartPos = Point3()
        self.camStartQuat = Quat()
        self.savedCamPos = None
        self.savedCamHpr = None
        self.smartCamWasOn = False
        self.savedGravity = None
        self.savedProps = None
        self.skipMouse = 2
        self.lastSend = 0.0
        self.lastFlags = None

    def startGlide(self):
        av = self.avatar
        if not self.canStartGlide():
            return
        self.notify.debug('startGlide')
        self._resetGlideState()
        self.gliding = True
        self.glideStartTime = globalClock.getFrameTime()
        walker = av.physControls
        self._geom = getattr(av, '_LocalAvatar__geom', None)

        # take over from the GravityWalker's movement task; keep its collision solids alive
        speeds = av.controlManager.getSpeeds() or (0.0, 0.0, 0.0)
        walker.disableAvatarControls()
        lifter = walker.lifter
        self.savedGravity = lifter.getGravity()
        vz = lifter.getVelocity()
        lifter.setGravity(0.0)
        lifter.setVelocity(0.0)

        # animation: stop speed-tracking, pose as airborne
        av.stopTrackAnimToSpeed()
        av.stopLookAround()
        av.stopJumpLandTask()
        av.b_setAnimState(C.GLIDE_ANIM_STATE, 1.0)

        # initial view = where the camera is currently looking
        fwd = render.getRelativeVector(camera, Vec3(0, 1, 0))
        yaw = math.degrees(math.atan2(-fwd.getX(), fwd.getY()))
        self.rawYaw = self.viewYaw = self.bodyYaw = yaw
        self.rawPitch = self.viewPitch = 0.0
        self.bodyPitch = 0.0

        # initial velocity: carry current motion, make sure there is some forward speed
        h = math.radians(av.getH(render))
        walkSpeed = abs(speeds[0]) if speeds else 0.0
        look = ElytraPhysics.lookVector(yaw, 0.0)
        self.vel = Vec3(-math.sin(h) * walkSpeed, math.cos(h) * walkSpeed, vz)
        hs = math.hypot(self.vel.getX(), self.vel.getY())
        if hs < C.START_MIN_SPEED:
            self.vel.setX(look[0] * C.START_MIN_SPEED)
            self.vel.setY(look[1] * C.START_MIN_SPEED)

        self._captureMouse()
        self._takeCamera()
        taskMgr.remove(self.updateTask)
        taskMgr.add(self._update, self.updateTask, priority=25)
        self._sendState(force=True)

    def stopGlide(self, reason='land', reenable=True, animateCamera=True):
        if not self.gliding:
            return
        self.notify.debug('stopGlide: %s' % reason)
        av = self.avatar
        self.gliding = False
        taskMgr.remove(self.updateTask)
        self.effects.cleanup()
        self._releaseMouse()
        ElytraPose.clearBodyPose(av)
        av.setP(0)
        av.setR(0)
        self.boostTime = 0.0
        if not av.isEmpty():
            walker = av.physControls
            if self.savedGravity is not None:
                walker.lifter.setGravity(self.savedGravity)
            walker.lifter.setVelocity(0.0)
            if reenable:
                walker.enableAvatarControls()
                onGround = walker.lifter.isOnGround()
                # let the walker report a landing if we cancelled mid-air
                walker.isAirborne = 0 if onGround or reason == 'land' else 1
        self._returnCamera(animate=animateCamera and reenable)
        self.lastStopTime = globalClock.getFrameTime()
        if reenable and not av.isEmpty():
            av.startTrackAnimToSpeed()
            if reason == 'cancel':
                av.b_setAnimState('jumpAirborne', 1.0)
        self._sendState(force=True)

    def onControlsDisabled(self):
        """Called when something else (door, gui, teleport...) disables avatar controls."""
        if self.gliding:
            self.stopGlide(reason='controlsDisabled', reenable=False, animateCamera=False)
        self.lastStopTime = globalClock.getFrameTime()

    # ------------------------------------------------------------------ mouse
    def _captureMouse(self):
        win = base.win
        props = WindowProperties()
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_confined)
        win.requestProperties(props)
        self.skipMouse = 2
        self._mouseCaptured = True
        self._recenter()

    def _releaseMouse(self):
        if getattr(self, '_mouseCaptured', False):
            self._mouseCaptured = False
            props = WindowProperties()
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            base.win.requestProperties(props)

    def _recenter(self):
        win = base.win
        win.movePointer(0, win.getXSize() // 2, win.getYSize() // 2)

    def _mouseDelta(self):
        win = base.win
        if not win.getProperties().getForeground():
            self.skipMouse = 2
            return 0.0, 0.0
        ptr = win.getPointer(0)
        cx, cy = win.getXSize() // 2, win.getYSize() // 2
        dx = dy = 0.0
        if ptr.getInWindow() and self.skipMouse <= 0:
            dx = ptr.getX() - cx
            dy = ptr.getY() - cy
        elif self.skipMouse > 0:
            self.skipMouse -= 1
        win.movePointer(0, cx, cy)
        return dx, dy

    # ---------------------------------------------------------------- camera
    def _takeCamera(self):
        av = self.avatar
        self.savedCamPos = Point3(camera.getPos())
        self.savedCamHpr = Vec3(camera.getHpr())
        self.smartCamWasOn = bool(getattr(av, '_smartCamEnabled', False))
        if self.smartCamWasOn:
            taskMgr.remove(av.taskName('updateSmartCamera'))
        taskMgr.remove(self.camReturnTask)
        camera.wrtReparentTo(render)
        self.camStartPos = Point3(camera.getPos(render))
        self.camStartQuat = Quat(camera.getQuat(render))
        self.camBlendT = 0.0

    def _chasePose(self, dt):
        av = self.avatar
        quat = Quat()
        quat.setHpr(Vec3(self.viewYaw, self.viewPitch, 0))
        pivot = av.getPos(render) + Vec3(0, 0, av.getHeight() * 0.55)
        look = Vec3(*ElytraPhysics.lookVector(self.viewYaw, self.viewPitch))
        dist = C.CAMERA_DIST
        want = pivot - look * dist + Vec3(0, 0, C.CAMERA_UP)
        # pull the camera in if geometry is in the way
        entries = self._sweep(pivot, want, OTPGlobals.WallBitmask | OTPGlobals.CameraBitmask)
        if entries:
            hit = entries[0].getSurfacePoint(render)
            want = pivot + (hit - pivot) * 0.9
            if (want - pivot).length() < 2.5:
                want = pivot - look * 2.5
        return want, quat

    def _updateCamera(self, dt):
        want, quat = self._chasePose(dt)
        self.camBlendT += dt
        s = _smoothstep(self.camBlendT / C.CAMERA_BLEND_IN)
        pos = self.camStartPos + (want - self.camStartPos) * s
        camera.setPos(render, pos)
        camera.setQuat(render, _nlerp(self.camStartQuat, quat, s))

    def _returnCamera(self, animate):
        av = self.avatar
        if self.savedCamPos is None:
            return
        taskMgr.remove(self.camReturnTask)
        camera.wrtReparentTo(av)
        if not animate:
            self._finishCameraReturn()
            return
        self._retStartPos = Point3(camera.getPos())
        self._retStartQuat = Quat(camera.getQuat())
        endQuat = Quat()
        endQuat.setHpr(self.savedCamHpr)
        self._retEndQuat = endQuat
        self._retT = 0.0
        taskMgr.add(self._camReturnUpdate, self.camReturnTask, priority=46)

    def _camReturnUpdate(self, task):
        self._retT += globalClock.getDt()
        s = _smoothstep(self._retT / C.CAMERA_BLEND_OUT)
        camera.setPos(self._retStartPos + (self.savedCamPos - self._retStartPos) * s)
        camera.setQuat(_nlerp(self._retStartQuat, self._retEndQuat, s))
        if self._retT >= C.CAMERA_BLEND_OUT:
            self._finishCameraReturn()
            return task.done
        return task.cont

    def _finishCameraReturn(self):
        av = self.avatar
        taskMgr.remove(self.camReturnTask)
        if av.isEmpty() or self.savedCamPos is None:
            return
        camera.reparentTo(av)
        camera.setPos(self.savedCamPos)
        camera.setHpr(self.savedCamHpr)
        if self.smartCamWasOn and getattr(av, '_smartCamEnabled', False):
            taskName = av.taskName('updateSmartCamera')
            taskMgr.remove(taskName)
            taskMgr.add(av.updateSmartCamera, taskName, priority=47)
        self.savedCamPos = None

    # --------------------------------------------------------- collision sweep
    def _sweep(self, a, b, mask=None):
        if mask is None:
            mask = OTPGlobals.WallBitmask | OTPGlobals.FloorBitmask
        if self._segNode is None:
            self._segment = CollisionSegment(Point3(0, 0, 0), Point3(0, 0, 1))
            self._segNode = CollisionNode('elytraSweep')
            self._segNode.addSolid(self._segment)
            self._segNode.setIntoCollideMask(BitMask32.allOff())
            self._segNP = render.attachNewNode(self._segNode)
            self._segQueue = CollisionHandlerQueue()
            self._segTrav = CollisionTraverser('elytraSweep')
            self._segTrav.addCollider(self._segNP, self._segQueue)
        if (b - a).lengthSquared() < 1e-8:
            return []
        self._segNode.setFromCollideMask(mask)
        self._segment.setPointA(a)
        self._segment.setPointB(b)
        self._segTrav.traverse(self._geom if self._geom is not None and not self._geom.isEmpty() else render)
        self._segQueue.sortEntries()
        return [self._segQueue.getEntry(i) for i in range(self._segQueue.getNumEntries())]

    def _destroySweep(self):
        if self._segNP is not None:
            self._segNP.removeNode()
        self._segNP = self._segNode = self._segQueue = self._segTrav = None

    def _moveAndCollide(self, dt):
        """Move by vel*dt. Returns True if we touched down on a floor."""
        av = self.avatar
        p0 = av.getPos(render)
        step = self.vel * dt
        length = step.length()
        if length < 1e-5:
            return False
        direction = step / length
        p1 = p0 + step
        chest = av.getHeight() * 0.6
        best = None
        for off, reach in ((0.15, 0.0), (chest, 1.3)):
            up = Vec3(0, 0, off)
            entries = self._sweep(p0 + up, p1 + up + direction * reach)
            for e in entries:
                n = e.getSurfaceNormal(render)
                if n.dot(direction) >= 0.0:
                    continue
                d = (e.getSurfacePoint(render) - (p0 + up)).length()
                if best is None or d < best[0]:
                    best = (d, e, off, n)
                break
        if best is None:
            av.setFluidPos(render, p1)
            return False
        d, entry, off, n = best
        hit = entry.getSurfacePoint(render)
        n = Vec3(n)
        n.normalize()
        if n.getZ() >= OTPGlobals.ToonStandableGround and self.vel.getZ() <= 0.0:
            av.setFluidPos(render, Point3(hit.getX(), hit.getY(), hit.getZ() + 0.05))
            return True
        # slide along walls / ceilings: keep the tangential velocity, drop the part into the surface
        into = self.vel.dot(n)
        if into < 0.0:
            self.vel -= n * into
        pos = hit - Vec3(0, 0, off) + n * 1.0
        av.setFluidPos(render, Point3(pos))
        return False

    # ------------------------------------------------------------------ update
    def _update(self, task):
        av = self.avatar
        if av.isEmpty():
            self.stopGlide(reason='gone', reenable=False, animateCamera=False)
            return task.done
        dt = min(globalClock.getDt(), C.MAX_DT)
        now = globalClock.getFrameTime()

        # landing detected by the walker's floor lifter
        if now - self.glideStartTime > 0.2 and av.physControls.lifter.isOnGround():
            self.stopGlide(reason='land')
            return task.done

        # mouse look
        dx, dy = self._mouseDelta()
        self.rawYaw -= dx * C.MOUSE_SENSITIVITY
        self.rawPitch = max(-C.PITCH_LIMIT, min(C.PITCH_LIMIT, self.rawPitch - dy * C.MOUSE_SENSITIVITY))
        a = 1.0 - math.exp(-dt / max(C.CAMERA_SMOOTH_TIME, 1e-4))
        prevYaw = self.viewYaw
        self.viewYaw += _angleDiff(self.rawYaw, self.viewYaw) * a
        self.viewPitch += (self.rawPitch - self.viewPitch) * a
        if dt > 0:
            rate = _angleDiff(self.viewYaw, prevYaw) / dt
            self.yawRate += (rate - self.yawRate) * (1.0 - math.exp(-6.0 * dt))

        # physics
        self.boostTime = max(0.0, self.boostTime - dt)
        v = ElytraPhysics.stepFlight((self.vel.getX(), self.vel.getY(), self.vel.getZ()),
                                     self.viewYaw, self.viewPitch, dt, self.boostTime)
        self.vel = Vec3(*v)
        landed = self._moveAndCollide(dt)
        av.physControls.lifter.setVelocity(0.0)

        # body orientation
        kYaw = 1.0 - math.exp(-C.BODY_YAW_RESPONSE * dt)
        kPitch = 1.0 - math.exp(-C.BODY_PITCH_RESPONSE * dt)
        kBank = 1.0 - math.exp(-C.BODY_BANK_RESPONSE * dt)
        self.bodyYaw += _angleDiff(self.viewYaw, self.bodyYaw) * kYaw
        self.bodyPitch += (self.viewPitch - self.bodyPitch) * kPitch
        bankTarget = max(-C.BANK_MAX, min(C.BANK_MAX, -self.yawRate * C.BANK_PER_YAW_RATE))
        self.bodyBank += (bankTarget - self.bodyBank) * kBank
        av.setH(render, self.bodyYaw)
        ElytraPose.applyBodyPose(av, self.bodyPitch, self.bodyBank)

        self._updateCamera(dt)
        self._sendState()
        if landed:
            self.stopGlide(reason='land')
            return task.done
        return task.cont

    # ------------------------------------------------------------------ boost
    def boost(self):
        now = globalClock.getFrameTime()
        if not self.gliding or now - self.lastBoostTime < C.BOOST_COOLDOWN:
            return
        self.lastBoostTime = now
        self.boostTime = C.BOOST_DURATION
        self.effects.playBoost()
        self.avatar.sendUpdate('setElytraBoost', [])

    # ---------------------------------------------------------------- network
    def _sendState(self, force=False):
        av = self.avatar
        if av.isEmpty() or not self.hasWings:
            return
        now = globalClock.getFrameTime()
        flags = FLAG_EQUIPPED | (FLAG_GLIDING if self.gliding else 0)
        if not force and flags == self.lastFlags and now - self.lastSend < C.NET_SEND_INTERVAL:
            return
        self.lastFlags = flags
        self.lastSend = now
        try:
            av.sendUpdate('setElytraState', [flags, float(self.bodyPitch), float(self.bodyBank)])
        except Exception:
            self.notify.warning('could not send elytra state', exc_info=True)

    # ---------------------------------------------------------------- cleanup
    def destroy(self):
        if self.gliding:
            self.stopGlide(reason='destroy', reenable=False, animateCamera=False)
        self._finishCameraReturn()
        self.ignoreAll()
        taskMgr.remove(self.updateTask)
        taskMgr.remove(self.refreshTask)
        taskMgr.remove(self.camReturnTask)
        self.effects.cleanup()
        self._destroySweep()
        self._releaseMouse()
