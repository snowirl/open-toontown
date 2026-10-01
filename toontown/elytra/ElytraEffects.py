"""Visuals for the firework-style boost: hand-held TNT, sound, and a short smoke/fire trail.

Every boost is a self-contained _Burst that removes all of its own nodes, particle
effects, intervals and tasks when it ends (or when ElytraEffects.cleanup() is called).
"""
from panda3d.core import Vec3, Point3, NodePath
from direct.interval.IntervalGlobal import Sequence, Func, Wait
from direct.particles import ParticleEffect
from direct.directnotify import DirectNotifyGlobal
from toontown.battle import BattleParticles
from . import ElytraConstants as C

notify = DirectNotifyGlobal.directNotify.newCategory('ElytraEffects')


def _loadEffect(ptf, texture):
    effect = BattleParticles.loadParticleFile(ptf)
    if effect is None:
        return None
    particles = effect.getParticlesNamed('particles-1')
    if particles is not None and texture:
        particles.getRenderer().setTextureFromNode(texture, '**/*')
    return effect


class _Burst:
    """One firework boost's visuals."""

    def __init__(self, owner, toon):
        self.owner = owner
        self.toon = toon
        self.dead = False
        self.tnt = None
        self.tntSeq = None
        self.effects = []
        self.endTaskName = 'elytraBurstEnd-%d' % id(self)
        # Anchor lives in render; fire/smoke emit from it opposite to the flight direction.
        self.anchor = render.attachNewNode('elytraTrailAnchor')
        self.smokeNode = self.anchor.attachNewNode('smoke')
        self.fireNode = self.anchor.attachNewNode('fire')
        self.fireNode.setBin('fixed', 1)
        self.fireNode.setDepthWrite(1)
        self.smokeNode.setBin('fixed', 1)
        self.smokeNode.setDepthWrite(0)
        self._start()

    def _start(self):
        toon = self.toon
        # --- hand-held TNT ---
        hands = toon.getRightHands()
        tnt = loader.loadModel(C.TNT_MODEL, okMissing=True)
        if tnt and hands:
            self.tnt = tnt
            tnt.reparentTo(hands[0])
            tnt.setScale(0.6)
            tnt.setPos(0, 0.2, 0)
            tnt.setHpr(0, 90, 0)
            tip = tnt.find('**/' + C.TNT_TIP_JOINT)
            sparks = BattleParticles.loadParticleFile(C.PTF_SPARKS)
            if sparks is not None:
                sparks.start(tip if not tip.isEmpty() else tnt)
                self.effects.append(sparks)
            self.tntSeq = Sequence(Wait(C.TNT_IN_HAND_TIME), Func(self._dropTnt))
            self.tntSeq.start()
        # --- sound ---
        for path, vol in ((C.SND_TNT_LIGHT, 0.8), (C.SND_LAUNCH, 1.0), (C.SND_POP, 0.6)):
            sfx = loader.loadSfx(path)
            if sfx:
                base.playSfx(sfx, node=toon, volume=vol)
        # --- trail ---
        for ptf, tex, parent in ((C.PTF_SMOKE, C.TEX_SMOKE, self.smokeNode),
                                 (C.PTF_FIRE, C.TEX_FIRE, self.fireNode)):
            effect = _loadEffect(ptf, tex)
            if effect is None:
                continue
            effect.start(parent=parent, renderParent=render)
            self.effects.append(effect)
        self._updateAnchor()
        taskMgr.doMethodLater(C.BOOST_DURATION, self._stopEmitting, self.endTaskName + '-stop')
        taskMgr.doMethodLater(C.TRAIL_DURATION, self._finish, self.endTaskName)

    def _dropTnt(self):
        if self.tnt:
            self.tnt.removeNode()
            self.tnt = None

    def _updateAnchor(self):
        toon = self.toon
        geom = toon.getGeomNode()
        if geom.isEmpty() or toon.isEmpty():
            return
        # body "up" axis is the flight direction while gliding
        direction = render.getRelativeVector(geom, Vec3(0, 0, 1))
        if direction.lengthSquared() < 1e-6:
            return
        direction.normalize()
        pos = toon.getPos(render) + Vec3(0, 0, toon.getHeight() * 0.55) - direction * 1.0
        self.anchor.setPos(render, pos)
        # emitter local -Z points opposite to the flight direction
        self.anchor.lookAt(render, pos + direction)
        self.anchor.setP(self.anchor, -90)

    def update(self):
        if not self.dead:
            self._updateAnchor()

    def _stopEmitting(self, task=None):
        for effect in self.effects:
            try:
                effect.disable()
            except Exception:
                pass
        return task.done if task else None

    def _finish(self, task=None):
        self.destroy()
        return task.done if task else None

    def destroy(self):
        if self.dead:
            return
        self.dead = True
        taskMgr.remove(self.endTaskName)
        taskMgr.remove(self.endTaskName + '-stop')
        if self.tntSeq:
            self.tntSeq.pause()
            self.tntSeq = None
        self._dropTnt()
        for effect in self.effects:
            try:
                effect.cleanup()
            except Exception:
                pass
        self.effects = []
        if not self.anchor.isEmpty():
            self.anchor.removeNode()
        self.owner._burstDone(self)


class ElytraEffects:
    """Per-toon manager of boost visuals."""

    def __init__(self, toon):
        self.toon = toon
        self.bursts = []
        self.taskName = 'elytraEffects-%d' % id(self)

    def playBoost(self):
        if self.toon.isEmpty():
            return
        burst = _Burst(self, self.toon)
        self.bursts.append(burst)
        if len(self.bursts) == 1:
            taskMgr.add(self._update, self.taskName, priority=48)

    def _update(self, task):
        for burst in list(self.bursts):
            burst.update()
        return task.cont if self.bursts else task.done

    def _burstDone(self, burst):
        if burst in self.bursts:
            self.bursts.remove(burst)
        if not self.bursts:
            taskMgr.remove(self.taskName)

    def cleanup(self):
        for burst in list(self.bursts):
            burst.destroy()
        self.bursts = []
        taskMgr.remove(self.taskName)

    def activeCount(self):
        return len(self.bursts)
