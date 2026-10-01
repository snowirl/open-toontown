"""World pickup for the Airplane Wings (the visible Elytra item).

Reusable: AirplaneWingsPickupManager.spawn(...) can be called from any playground.
"""
from panda3d.core import Point3, Vec3, NodePath, TextNode, CollisionRay, CollisionNode, CollisionHandlerQueue, CollisionTraverser, BitMask32
from direct.showbase.DirectObject import DirectObject
from direct.interval.IntervalGlobal import Sequence, Parallel, LerpHprInterval, LerpPosInterval
from direct.directnotify import DirectNotifyGlobal
from otp.otpbase import OTPGlobals
from toontown.toon import ToonDNA
from toontown.toonbase import ToontownGlobals
from . import ElytraConstants as C


def findGroundZ(geom, x, y, default):
    """Cast a ray down at (x, y) against the playground floor collision."""
    if geom is None or geom.isEmpty():
        return default
    ray = CollisionRay(x, y, 200.0, 0, 0, -1)
    node = CollisionNode('elytraPickupGround')
    node.addSolid(ray)
    node.setFromCollideMask(OTPGlobals.FloorBitmask)
    node.setIntoCollideMask(BitMask32.allOff())
    np = render.attachNewNode(node)
    queue = CollisionHandlerQueue()
    trav = CollisionTraverser('elytraPickupGround')
    trav.addCollider(np, queue)
    trav.traverse(geom)
    best = None
    for i in range(queue.getNumEntries()):
        z = queue.getEntry(i).getSurfacePoint(render).getZ()
        if z < 40.0 and (best is None or z > best):
            best = z
    np.removeNode()
    return default if best is None else best


class AirplaneWingsPickup(DirectObject):
    notify = DirectNotifyGlobal.directNotify.newCategory('AirplaneWingsPickup')

    def __init__(self, groundPos, onCollect):
        self.onCollect = onCollect
        self.collected = False
        self.root = render.attachNewNode('AirplaneWingsPickup')
        self.root.setPos(render, groundPos)
        self.anim = None
        self.checkTask = 'airplaneWingsPickupCheck-%d' % id(self)
        self._load()

    def _load(self):
        model = loader.loadModel(ToonDNA.BackpackModels[C.WINGS_BACKPACK_IDX])
        hoverRoot = self.root.attachNewNode('hover')
        hoverRoot.setZ(C.PICKUP_HOVER_HEIGHT)
        model.reparentTo(hoverRoot)
        model.setScale(C.PICKUP_SCALE)
        model.setHpr(180, 0, 0)
        model.setTwoSided(True)
        text = TextNode('airplaneWingsLabel')
        text.setText('Airplane Wings')
        text.setAlign(TextNode.ACenter)
        text.setFont(ToontownGlobals.getSignFont())
        text.setTextColor(1, 0.9, 0.2, 1)
        text.setShadow(0.05, 0.05)
        text.setShadowColor(0, 0, 0, 1)
        label = self.root.attachNewNode(text)
        label.setScale(0.8)
        label.setZ(C.PICKUP_HOVER_HEIGHT + 2.2)
        label.setBillboardPointEye()
        label.setLightOff()
        self.anim = Parallel(
            LerpHprInterval(model, 4.0, Vec3(180 + 360, 0, 0), startHpr=Vec3(180, 0, 0)),
            Sequence(LerpPosInterval(hoverRoot, 1.0, Point3(0, 0, C.PICKUP_HOVER_HEIGHT + 0.5),
                                     startPos=Point3(0, 0, C.PICKUP_HOVER_HEIGHT), blendType='easeInOut'),
                     LerpPosInterval(hoverRoot, 1.0, Point3(0, 0, C.PICKUP_HOVER_HEIGHT), blendType='easeInOut')))
        self.anim.loop()
        taskMgr.doMethodLater(0.1, self._check, self.checkTask)

    def _check(self, task):
        if self.collected or self.root.isEmpty():
            return task.done
        av = getattr(base, 'localAvatar', None)
        if av is not None and not av.isEmpty() and getattr(av, 'avatarControlsEnabled', 0):
            dist = (av.getPos(render) - self.root.getPos(render) - Vec3(0, 0, 1.0)).length()
            if dist < C.PICKUP_RADIUS:
                self.collect()
                return task.done
        return task.again

    def collect(self):
        if self.collected:
            return
        callback = self.onCollect
        self.destroy()
        if callback:
            callback()

    def destroy(self):
        self.collected = True
        taskMgr.remove(self.checkTask)
        if self.anim:
            self.anim.finish()
            self.anim = None
        if self.root and not self.root.isEmpty():
            self.root.removeNode()
        self.root = NodePath()
        self.ignoreAll()


class AirplaneWingsPickupManager:
    """Spawns the pickup in a playground unless this session already collected it."""
    pickup = None

    @classmethod
    def spawn(cls, playground, groundXY):
        cls.remove()
        controller = getattr(base.localAvatar, 'elytra', None)
        if controller is not None and controller.hasWings:
            return None
        z = findGroundZ(playground.loader.geom, groundXY.getX(), groundXY.getY(), groundXY.getZ())
        cls.pickup = AirplaneWingsPickup(Point3(groundXY.getX(), groundXY.getY(), z), cls._collected)
        return cls.pickup

    @classmethod
    def _collected(cls):
        cls.pickup = None
        base.localAvatar.elytra.equipWings(announce=True)

    @classmethod
    def remove(cls):
        if cls.pickup is not None:
            cls.pickup.destroy()
            cls.pickup = None
