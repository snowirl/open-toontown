"""Procedural body orientation for a gliding Toon (works for local and remote toons).

Only the Toon's geometry node is rotated; the avatar node itself keeps P = R = 0 so
the collision solids, shadow and camera rig are untouched.
"""
from panda3d.core import Quat, Vec3
from . import ElytraConstants as C


def applyBodyPose(toon, pitch, bank=0.0):
    """Lay the Toon flat in the flight direction. pitch: degrees, + = nose up."""
    geom = toon.getGeomNode()
    if geom.isEmpty():
        return
    if not hasattr(toon, '_elytraBaseTransform'):
        toon._elytraBaseTransform = geom.getTransform()
    qBank = Quat()
    qBank.setHpr(Vec3(bank, 0, 0))
    qPitch = Quat()
    qPitch.setHpr(Vec3(0, pitch - 90.0, 0))
    q = qBank * qPitch
    pivot = Vec3(0, 0, toon.getHeight() * 0.55)
    geom.setQuat(q)
    geom.setPos(pivot - q.xform(pivot))


def clearBodyPose(toon):
    base = getattr(toon, '_elytraBaseTransform', None)
    if base is not None:
        geom = toon.getGeomNode()
        if not geom.isEmpty():
            geom.setTransform(base)
        del toon._elytraBaseTransform
