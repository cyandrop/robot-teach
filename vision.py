# -*- coding: utf-8 -*-
"""
视觉模块：从仿真相机取图 → 颜色识别 → 像素+深度反投影成三维点 → 求质心坐标。

核心思路（报告里可以这么写）：
1. PyBullet 渲染出相机画面与深度图（代替真实 RGB-D 相机）
2. OpenCV 在 HSV 空间做颜色分割，锁定目标色块的像素区域
3. 把区域内每个像素连同深度值反投影回三维空间，得到一小片「点云」，
   取其质心作为物体坐标 —— 对方块取最高层点（顶面），对区域取全部点。
   这就是 RGB-D 视觉里常用的「点云质心定位」方法。

注意：pybullet 返回的 view/projection 矩阵是「列主序」存储，
直接 reshape 得到的是转置，必须先转置再用（这个坑已实测踩过）。
"""

import numpy as np
import cv2
import pybullet as p

from config import (CAM_EYE, CAM_TARGET, CAM_UP, CAM_FOV, CAM_W, CAM_H,
                    CAM_NEAR, CAM_FAR, HSV_RANGES, MIN_CONTOUR_AREA,
                    TABLE_CENTER, TABLE_HALF)


class Camera:
    def __init__(self):
        self.view = p.computeViewMatrix(CAM_EYE, CAM_TARGET, CAM_UP)
        self.proj = p.computeProjectionMatrixFOV(CAM_FOV, CAM_W / CAM_H,
                                                 CAM_NEAR, CAM_FAR)
        V = np.array(self.view, dtype=float).reshape(4, 4)
        P = np.array(self.proj, dtype=float).reshape(4, 4)
        self.m = P.T @ V.T            # clip = m @ world（列向量约定）
        self.m_inv = np.linalg.inv(self.m)

    def render(self):
        """返回 (RGB 图像, 深度图)"""
        try:
            _, h, rgb, depth, _ = p.getCameraImage(
                CAM_W, CAM_H, self.view, self.proj,
                renderer=p.ER_BULLET_HARDWARE_OPENGL)
        except Exception:
            _, h, rgb, depth, _ = p.getCameraImage(
                CAM_W, CAM_H, self.view, self.proj,
                renderer=p.ER_TINY_RENDERER)
        rgb = np.asarray(rgb)
        if rgb.ndim == 1:
            rgb = rgb.reshape(h, CAM_W, -1)
        rgb = rgb[:, :, :3].astype(np.uint8)
        depth = np.asarray(depth, dtype=float).reshape(h, CAM_W)
        return rgb, depth

    def world_to_pixel(self, xyz):
        """世界坐标 → 像素坐标（自检用）"""
        v = self.m @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
        v = v / v[3]
        return float((v[0] * 0.5 + 0.5) * CAM_W), float((0.5 - v[1] * 0.5) * CAM_H)

    def unproject_points(self, us, vs, depths):
        """批量：像素坐标 + 深度 → 世界坐标点云，返回 (N,3)"""
        us = np.asarray(us, float)
        vs = np.asarray(vs, float)
        depths = np.asarray(depths, float)
        nx = 2.0 * (us + 0.5) / CAM_W - 1.0
        ny = 1.0 - 2.0 * (vs + 0.5) / CAM_H
        nz = 2.0 * depths - 1.0
        clip = self.m_inv @ np.vstack([nx, ny, nz, np.ones_like(nx)])
        return (clip[:3] / clip[3]).T


def _mask_for(hsv, name):
    mask = None
    for lo, hi in HSV_RANGES[name]:
        m = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        mask = m if mask is None else cv2.bitwise_or(mask, m)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def _inside_table(xy):
    x, y = xy
    return (abs(x - TABLE_CENTER[0]) <= TABLE_HALF[0] + 0.02 and
            abs(y - TABLE_CENTER[1]) <= TABLE_HALF[1] + 0.02)


def detect(cam, rgb, depth, name, is_block, top_layer=0.012):
    """
    识别某个颜色的目标，返回 (世界坐标 (x,y,z), 调试信息 dict)。
    is_block=True 时只取点云最高一层（方块顶面），压掉侧面带来的偏移。
    """
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = _mask_for(hsv, name)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_area = None, 0.0
    for c in contours:
        area = cv2.contourArea(c)
        if area > best_area:
            best, best_area = c, area
    dbg = {"像素数": 0, "点云数": 0}
    if best is None or best_area < MIN_CONTOUR_AREA:
        dbg["原因"] = "无足够大的色块"
        return None, dbg

    fill = np.zeros(mask.shape, np.uint8)
    cv2.drawContours(fill, [best], -1, 255, -1)
    vs, us = np.nonzero(fill)          # 行号=像素v，列号=像素u
    dbg["像素数"] = int(len(us))
    pts = cam.unproject_points(us, vs, depth[vs, us])
    dbg["点云数"] = int(len(pts))
    if len(pts) == 0:
        dbg["原因"] = "点云为空"
        return None, dbg

    if is_block:
        zmax = pts[:, 2].max()
        top = pts[pts[:, 2] > zmax - top_layer]
        dbg["点云数_顶面"] = int(len(top))
        pts = top if len(top) >= 5 else pts

    center = pts[:, :2].mean(axis=0)
    dbg["像素中心"] = (float(us.mean()), float(vs.mean()))
    if not _inside_table(center):
        dbg["原因"] = "反投影落在桌面外 %s" % [round(v, 3) for v in center]
        return None, dbg
    return (float(center[0]), float(center[1]), float(pts[:, 2].mean())), dbg


def draw_overlay(img_rgb, points):
    """在图像上画标记，用于演示录像时展示识别效果"""
    out = img_rgb.copy()
    for (u, v), color, label in points:
        cv2.circle(out, (int(u), int(v)), 6, color, 2)
        cv2.putText(out, label, (int(u) + 8, int(v) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    return out
