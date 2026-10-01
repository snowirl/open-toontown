"""Remote-toon side of Elytra synchronisation (what other players see)."""
import math
from direct.task import Task
from . import ElytraConstants as C
from . import ElytraPose
from .ElytraEffects import ElytraEffects

FLAG_EQUIPPED = 1
FLAG_GLIDING = 2


class ElytraRemoteView:

    def __init__(self, toon):
        self.toon = toon
        self.gliding = False
        self.pitch = 0.0
        self.bank = 0.0
        self.targetPitch = 0.0
        self.targetBank = 0.0
        self.effects = ElytraEffects(toon)
        self.taskName = 'elytraRemotePose-%d' % id(self)

    def setState(self, flags, pitch, bank):
        toon = self.toon
        if flags & FLAG_EQUIPPED and tuple(toon.getBackpack()) != C.WINGS_STYLE:
            toon.setBackpack(*C.WINGS_STYLE)
        self.targetPitch = pitch
        self.targetBank = bank
        gliding = bool(flags & FLAG_GLIDING)
        if gliding and not self.gliding:
            self.pitch = pitch
            self.bank = bank
            ElytraPose.applyBodyPose(toon, self.pitch, self.bank)
            taskMgr.add(self._update, self.taskName, priority=40)
        elif not gliding and self.gliding:
            self.stopGlide()
        self.gliding = gliding

    def _update(self, task):
        dt = globalClock.getDt()
        k = 1.0 - math.exp(-C.BODY_PITCH_RESPONSE * dt)
        self.pitch += (self.targetPitch - self.pitch) * k
        self.bank += (self.targetBank - self.bank) * k
        ElytraPose.applyBodyPose(self.toon, self.pitch, self.bank)
        return Task.cont

    def stopGlide(self):
        taskMgr.remove(self.taskName)
        ElytraPose.clearBodyPose(self.toon)

    def boost(self):
        self.effects.playBoost()

    def cleanup(self):
        self.stopGlide()
        self.effects.cleanup()
        self.gliding = False


def getRemoteView(toon):
    view = getattr(toon, '_elytraRemoteView', None)
    if view is None:
        view = ElytraRemoteView(toon)
        toon._elytraRemoteView = view
    return view


def cleanupRemoteView(toon):
    view = getattr(toon, '_elytraRemoteView', None)
    if view is not None:
        view.cleanup()
        toon._elytraRemoteView = None
