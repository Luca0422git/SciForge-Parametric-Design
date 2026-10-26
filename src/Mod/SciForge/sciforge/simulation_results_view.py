# SPDX-License-Identifier: LGPL-2.1-or-later
"""What the RESULTS tab draws: the coloured result on the 3D view (SciForge's own Coin nodes,
never document objects: nothing of it lands in the undo history or the file), and the Qt
pieces floating over the view: the legend, the min / max and probe tags, the animation bar.

The result is drawn from the outer surface of the solve's mesh (simulation_results.ResultData):
one texture coordinate per surface node picks its colour from a colour map texture, so the
colours between two nodes follow the map (blue, cyan, green, yellow, red) instead of a blend of
the two ends, the way Fusion's plots look. The controller (which result, which scale, when it
shows) is simulation_results_ui.py.
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import simulation_results_core as core
from . import warn
from .compat import QtCore, QtGui, QtWidgets

ROOT_NAME = "SciForgeSimResults"


def _alive(widget):
    try:
        if widget is None:
            return False
        widget.objectName()
        return True
    except (RuntimeError, AttributeError):
        return False


def _np():
    import numpy

    return numpy


def _ints(field, values):
    """Fill a Coin integer list field from numpy ints (or a list)."""
    np = _np()
    data = np.asarray(values, dtype=np.int32).ravel()
    field.setNum(0)
    if len(data):
        try:
            field.setValues(0, len(data), data)
        except Exception:
            field.setValues(0, len(data), data.tolist())


def _floats(field, values, width):
    """Fill a Coin vector list field from an (n, width) array."""
    np = _np()
    data = np.asarray(values, dtype=np.float32).reshape((-1, width))
    field.setNum(len(data))
    if len(data):
        try:
            field.setValues(0, len(data), data)
        except Exception:
            field.setValues(0, len(data), data.tolist())


def _polylines(lines):
    """coordIndex of an SoIndexedLineSet for (k, w) polylines."""
    np = _np()
    lines = np.asarray(lines, dtype=np.int64)
    if lines.size == 0:
        return np.zeros(0, dtype=np.int32)
    sep = np.full((len(lines), 1), -1, dtype=np.int64)
    return np.hstack([lines, sep]).ravel()


def _faces(triangles):
    np = _np()
    tris = np.asarray(triangles, dtype=np.int64).reshape((-1, 3))
    sep = np.full((len(tris), 1), -1, dtype=np.int64)
    return np.hstack([tris, sep]).ravel()


class ResultDisplay:
    """The result drawn on the 3D view (SciForge's own Coin nodes).

    root
      result part (cut by the slice plane's clip when it clips)
        coordinates (the deformed surface nodes)
        faces: shape hints, material, colour map texture, texture coordinates, faces
        mesh lines (Show Mesh), outline (sharp) edges
        iso-surface (where the result shown has one value: one colour)
      cut face (the slice: coloured where the plane cuts the mesh)
      ghost (the undeformed model, see-through)
    """

    def __init__(self, data, surface=None):
        from pivy import coin

        np = _np()
        self.coin = coin
        self.data = data
        surf = data.surface if surface is None else surface  # (some bodies hidden: theirs)
        self.nodes = np.asarray(surf["nodes"], dtype=np.int64)
        self.triangles = np.asarray(surf["triangles"], dtype=np.int64)
        self.factor = 0.0
        self.positions = np.zeros(len(self.nodes))  # colour map position of each surface node
        self.views = []

        self.root = coin.SoSeparator()
        self.root.setName(ROOT_NAME)
        self.shift = coin.SoTranslation()  # Compare puts the studies side by side
        self.offset = np.zeros(3)
        self.root.addChild(self.shift)

        self.part_switch = coin.SoSwitch()  # off for a slice shown alone
        self.part_switch.whichChild = coin.SO_SWITCH_ALL
        part = coin.SoSeparator()
        self.part_switch.addChild(part)
        self.clip_switch = coin.SoSwitch()
        self.clip = coin.SoClipPlane()
        self.clip_switch.addChild(self.clip)
        self.clip_switch.whichChild = coin.SO_SWITCH_NONE
        part.addChild(self.clip_switch)
        self.coords = coin.SoCoordinate3()
        part.addChild(self.coords)

        faces = coin.SoSeparator()
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
        hints.creaseAngle = 0.6
        faces.addChild(hints)
        self.material = coin.SoMaterial()
        self.material.diffuseColor.setValue(0.92, 0.92, 0.92)
        self.material.ambientColor.setValue(0.45, 0.45, 0.45)
        self.material.specularColor.setValue(0.12, 0.12, 0.12)
        self.material.shininess.setValue(0.25)
        faces.addChild(self.material)
        self.texture = coin.SoTexture2()
        self.texture.wrapS = coin.SoTexture2.CLAMP
        self.texture.wrapT = coin.SoTexture2.CLAMP
        self.texture.model = coin.SoTexture2.MODULATE
        self.set_texture(core.texture_rows())
        faces.addChild(self.texture)
        self.texcoords = coin.SoTextureCoordinate2()
        faces.addChild(self.texcoords)
        binding = coin.SoTextureCoordinateBinding()
        binding.value = coin.SoTextureCoordinateBinding.PER_VERTEX_INDEXED
        faces.addChild(binding)
        offset = coin.SoPolygonOffset()  # the lines drawn over the faces stay on top
        offset.factor = 1.0
        offset.units = 1.0
        faces.addChild(offset)
        self.faceset = coin.SoIndexedFaceSet()
        index = _faces(self.triangles)
        # 6-node faces drawn with their quadratic shape functions (new points after the nodes)
        self.extra_nodes = self.extra_weights = None
        faces6 = surf.get("faces6")
        if faces6 is not None and len(faces6):
            drawn, self.extra_nodes, self.extra_weights = core.refine_quadratic(
                faces6, len(self.nodes)
            )
            self.drawn_triangles = drawn
        else:
            self.drawn_triangles = self.triangles
        drawn_index = _faces(self.drawn_triangles)
        _ints(self.faceset.coordIndex, drawn_index)
        _ints(self.faceset.textureCoordIndex, drawn_index)
        faces.addChild(self.faceset)
        part.addChild(faces)

        self.mesh_switch = coin.SoSwitch()
        self.mesh_switch.addChild(self._lines(surf["lines"], (0.1, 0.1, 0.12), 1.0))
        self.mesh_switch.whichChild = coin.SO_SWITCH_NONE
        part.addChild(self.mesh_switch)
        self.outline_switch = coin.SoSwitch()
        self.outline_switch.addChild(self._lines(surf["features"], (0.12, 0.13, 0.15), 1.4))
        self.outline_switch.whichChild = coin.SO_SWITCH_ALL
        part.addChild(self.outline_switch)

        # the iso-surface: one colour (the legend's at its value), lit from both sides, cut by
        # the slice plane's clip like the result
        self.iso_switch = coin.SoSwitch()
        iso = coin.SoSeparator()
        iso_hints = coin.SoShapeHints()
        iso_hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        iso_hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
        iso_hints.creaseAngle = 0.8
        iso.addChild(iso_hints)
        self.iso_material = coin.SoMaterial()
        self.iso_material.diffuseColor.setValue(0.9, 0.5, 0.2)
        self.iso_material.ambientColor.setValue(0.4, 0.4, 0.4)
        self.iso_material.specularColor.setValue(0.15, 0.15, 0.15)
        self.iso_material.shininess.setValue(0.3)
        iso.addChild(self.iso_material)
        self.iso_coords = coin.SoCoordinate3()
        iso.addChild(self.iso_coords)
        self.iso_faces = coin.SoFaceSet()
        iso.addChild(self.iso_faces)
        self.iso_switch.addChild(iso)
        self.iso_switch.whichChild = coin.SO_SWITCH_NONE
        part.addChild(self.iso_switch)
        self.iso_points = np.zeros((0, 3))  # (3 per triangle) as drawn
        self.iso_rest = np.zeros((0, 3))  # the same points on the unloaded part
        self.root.addChild(self.part_switch)

        # the slice plane's cut face: its own coordinates, coloured with the same map
        self.cap_switch = coin.SoSwitch()
        cap = coin.SoSeparator()
        cap_hints = coin.SoShapeHints()
        cap_hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        cap_hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE  # (lit from both sides)
        cap.addChild(cap_hints)
        self.cap_normal = coin.SoNormal()  # one normal: the flat cut face takes the light evenly
        self.cap_normal.vector.setValue(0.0, 0.0, 1.0)
        cap.addChild(self.cap_normal)
        cap_normal_binding = coin.SoNormalBinding()
        cap_normal_binding.value = coin.SoNormalBinding.OVERALL
        cap.addChild(cap_normal_binding)
        cap_material = coin.SoMaterial()  # (opaque even when the part is see-through)
        cap_material.diffuseColor.setValue(0.92, 0.92, 0.92)
        cap_material.ambientColor.setValue(0.45, 0.45, 0.45)
        cap_material.specularColor.setValue(0.12, 0.12, 0.12)
        cap.addChild(cap_material)
        cap.addChild(self.texture)
        self.cap_coords = coin.SoCoordinate3()
        self.cap_texcoords = coin.SoTextureCoordinate2()
        cap.addChild(self.cap_coords)
        cap.addChild(self.cap_texcoords)
        cap_binding = coin.SoTextureCoordinateBinding()
        cap_binding.value = coin.SoTextureCoordinateBinding.PER_VERTEX
        cap.addChild(cap_binding)
        cap_offset = coin.SoPolygonOffset()  # (the mesh lines drawn on it stay on top)
        cap_offset.factor = 1.0
        cap_offset.units = 1.0
        cap.addChild(cap_offset)
        self.cap_faces = coin.SoFaceSet()
        cap.addChild(self.cap_faces)
        # Mesh Lines: where the plane crosses the elements' faces
        self.cap_lines_switch = coin.SoSwitch()
        lines = coin.SoSeparator()
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        lines.addChild(light)
        lines_colour = coin.SoBaseColor()
        lines_colour.rgb.setValue(0.1, 0.1, 0.12)
        lines.addChild(lines_colour)
        lines_style = coin.SoDrawStyle()
        lines_style.lineWidth.setValue(1.0)
        lines.addChild(lines_style)
        self.cap_line_coords = coin.SoCoordinate3()
        lines.addChild(self.cap_line_coords)
        self.cap_line_set = coin.SoLineSet()
        lines.addChild(self.cap_line_set)
        self.cap_lines_switch.addChild(lines)
        self.cap_lines_switch.whichChild = coin.SO_SWITCH_NONE
        cap.addChild(self.cap_lines_switch)
        self.cap_line_count = 0
        # Vectors: the displacement's arrows on the cut, coloured like the result there
        self.vectors_switch = coin.SoSwitch()
        arrows = coin.SoSeparator()
        arrows_light = coin.SoLightModel()
        arrows_light.model = coin.SoLightModel.BASE_COLOR
        arrows.addChild(arrows_light)
        self.vector_material = coin.SoMaterial()
        arrows.addChild(self.vector_material)
        vector_binding = coin.SoMaterialBinding()
        vector_binding.value = coin.SoMaterialBinding.PER_PART
        arrows.addChild(vector_binding)
        arrows_style = coin.SoDrawStyle()
        arrows_style.lineWidth.setValue(2.0)
        arrows.addChild(arrows_style)
        self.vector_coords = coin.SoCoordinate3()
        arrows.addChild(self.vector_coords)
        self.vector_lines = coin.SoLineSet()
        arrows.addChild(self.vector_lines)
        self.vectors_switch.addChild(arrows)
        self.vectors_switch.whichChild = coin.SO_SWITCH_NONE
        cap.addChild(self.vectors_switch)
        self.vector_count = 0
        self.vector_segments = np.zeros((0, 2, 3))
        self.cap_switch.addChild(cap)
        self.cap_switch.whichChild = coin.SO_SWITCH_NONE
        self.root.addChild(self.cap_switch)
        self.cap_points = np.zeros((0, 3))
        self.cap_rest = np.zeros((0, 3))
        self.cap_values = np.zeros(0)
        self.cap_positions = np.zeros(0)

        # the undeformed model, see-through (Fusion's "show undeformed model")
        self.ghost_switch = coin.SoSwitch()
        ghost = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        ghost.addChild(pick)
        ghost_hints = coin.SoShapeHints()
        ghost_hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        ghost_hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
        ghost_hints.creaseAngle = 0.6
        ghost.addChild(ghost_hints)
        ghost_material = coin.SoMaterial()
        ghost_material.diffuseColor.setValue(0.62, 0.66, 0.72)
        ghost_material.transparency.setValue(0.78)
        ghost.addChild(ghost_material)
        self.ghost_coords = coin.SoCoordinate3()
        _floats(self.ghost_coords.point, data.points[self.nodes], 3)
        ghost.addChild(self.ghost_coords)
        ghost_faces = coin.SoIndexedFaceSet()
        _ints(ghost_faces.coordIndex, index)
        ghost.addChild(ghost_faces)
        ghost.addChild(self._lines(surf["features"], (0.45, 0.48, 0.55), 1.0))
        self.ghost_switch.addChild(ghost)
        self.ghost_switch.whichChild = coin.SO_SWITCH_NONE
        self.root.addChild(self.ghost_switch)

        self.set_factor(0.0)
        self.set_positions([0.0] * len(self.nodes))

    def _lines(self, lines, colour, width):
        coin = self.coin
        sep = coin.SoSeparator()
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        sep.addChild(light)
        base = coin.SoBaseColor()
        base.rgb.setValue(*colour)
        sep.addChild(base)
        style = coin.SoDrawStyle()
        style.lineWidth.setValue(width)
        sep.addChild(style)
        lineset = coin.SoIndexedLineSet()
        _ints(lineset.coordIndex, _polylines(lines))
        sep.addChild(lineset)
        return sep

    # -- in the view
    def attach(self, view):
        try:
            graph = view.getSceneGraph()
            if graph.findChild(self.root) < 0:
                graph.addChild(self.root)
            if view not in self.views:
                self.views.append(view)
        except Exception as exc:
            warn("results display: %s" % exc)

    def detach(self):
        for view in self.views:
            try:
                graph = view.getSceneGraph()
                if graph.findChild(self.root) >= 0:
                    graph.removeChild(self.root)
            except Exception:
                continue  # (the view closed with its document)
        self.views = []

    # -- what it shows
    def set_texture(self, data):
        self.texture.image.setValue(self.coin.SbVec2s(core.TEXELS, 2), 3, data)

    def set_positions(self, positions):
        """The colour map position (0..1, None = no value) of every surface node."""
        np = _np()
        self.positions = np.asarray(
            [np.nan if p is None else float(p) for p in positions], dtype=float
        ).reshape(-1)
        t = self.positions
        if self.extra_nodes is not None:
            t = np.concatenate([t, np.einsum("vk,vk->v", self.extra_weights, t[self.extra_nodes])])
        coords = np.empty((len(t), 2))
        missing = np.isnan(t)
        coords[:, 0] = np.where(missing, 0.5, np.clip(np.nan_to_num(t), 0.0, 1.0))
        coords[:, 1] = np.where(missing, 0.75, 0.25)  # (core.texture_coordinate's rows)
        _floats(self.texcoords.point, coords, 2)

    def _drawn(self, points):
        """The surface nodes' places, then the new points of the 6-node faces drawn smoothly."""
        np = _np()
        if self.extra_nodes is None:
            return points
        extra = np.einsum("vk,vkd->vd", self.extra_weights, points[self.extra_nodes])
        return np.vstack([points, extra])

    def set_factor(self, factor):
        """Draw the displacement `factor` times (0 = the undeformed shape)."""
        self.factor = float(factor)
        _floats(self.coords.point, self._drawn(self.surface_points()), 3)

    def surface_points(self):
        """(k, 3) places of the surface nodes as drawn now."""
        data = self.data
        return data.points[self.nodes] + self.factor * data.displacement[self.nodes]

    def node_place(self, index):
        """Where node `index` (of the whole mesh) is drawn now."""
        data = self.data
        return data.points[index] + self.factor * data.displacement[index] + self.offset

    def set_offset(self, offset):
        """Draw the whole result moved by `offset` (Compare)."""
        np = _np()
        self.offset = np.asarray(offset, dtype=float).reshape(3)
        self.shift.translation.setValue(*[float(c) for c in self.offset])

    def set_mesh(self, on):
        self.mesh_switch.whichChild = self.coin.SO_SWITCH_ALL if on else self.coin.SO_SWITCH_NONE

    def set_ghost(self, on):
        self.ghost_switch.whichChild = self.coin.SO_SWITCH_ALL if on else self.coin.SO_SWITCH_NONE

    def set_see_through(self, on):
        """The result drawn see-through (a slice shown alone inside it)."""
        self.material.transparency.setValue(0.8 if on else 0.0)

    def see_through(self):
        return self.material.transparency[0] > 0.0

    def mesh_shown(self):
        return self.mesh_switch.whichChild.getValue() != self.coin.SO_SWITCH_NONE

    def ghost_shown(self):
        return self.ghost_switch.whichChild.getValue() != self.coin.SO_SWITCH_NONE

    def set_clip(self, origin, normal):
        """Cut the result away on the far side of a plane (normal points to what is kept);
        None removes the cut."""
        coin = self.coin
        if origin is None:
            self.clip_switch.whichChild = coin.SO_SWITCH_NONE
            return
        n = App.Vector(*normal)
        if n.Length < 1e-12:
            self.clip_switch.whichChild = coin.SO_SWITCH_NONE
            return
        n.normalize()
        d = n.dot(App.Vector(*origin))
        self.clip.plane.setValue(coin.SbPlane(coin.SbVec3f(n.x, n.y, n.z), d))
        self.clip_switch.whichChild = coin.SO_SWITCH_ALL

    def clipped(self):
        return self.clip_switch.whichChild.getValue() != self.coin.SO_SWITCH_NONE

    def set_cap(self, triangles, values, positions, normal=None, rest=None):
        """The slice's cut face: triangles ((k, 3, 3) or [(p0, p1, p2)]), their values and
        colour map positions (flat, three per triangle), `normal` the plane's (the triangles
        face against it), `rest` the same points on the unloaded part (Point Probes). Empty
        hides it."""
        np = _np()
        coin = self.coin
        if not len(triangles):
            self.cap_switch.whichChild = coin.SO_SWITCH_NONE
            self.set_cap_lines([])
            self.set_vectors([])
            self.cap_points = np.zeros((0, 3))
            self.cap_rest = np.zeros((0, 3))
            self.cap_values = np.zeros(0)
            self.cap_positions = np.zeros(0)
            self.cap_faces.numVertices.setNum(0)
            return
        pts = np.asarray(triangles, dtype=float).reshape((-1, 3))
        self.cap_rest = (
            np.asarray(rest, dtype=float).reshape((-1, 3)) if rest is not None else pts.copy()
        )
        if normal is not None:
            n = App.Vector(*normal)
            if n.Length > 1e-12:
                n.normalize()
                self.cap_normal.vector.setValue(-n.x, -n.y, -n.z)
        self.cap_points = pts
        self.cap_values = np.asarray(values, dtype=float).ravel()
        self.cap_positions = np.asarray(
            [np.nan if p is None else p for p in positions], dtype=float
        )
        _floats(self.cap_coords.point, pts, 3)
        _floats(self.cap_texcoords.point, [core.texture_coordinate(p) for p in positions], 2)
        count = len(pts) // 3
        self.cap_faces.numVertices.setNum(count)
        self.cap_faces.numVertices.setValues(0, count, [3] * count)
        self.cap_switch.whichChild = coin.SO_SWITCH_ALL

    def cap_shown(self):
        return self.cap_switch.whichChild.getValue() != self.coin.SO_SWITCH_NONE

    def set_cap_lines(self, segments):
        """The mesh lines on the cut face: (s, 2, 3) segments; empty hides them."""
        np = _np()
        coin = self.coin
        segs = np.asarray(segments, dtype=float).reshape((-1, 3))
        self.cap_line_count = len(segs) // 2
        if not self.cap_line_count:
            self.cap_lines_switch.whichChild = coin.SO_SWITCH_NONE
            self.cap_line_set.numVertices.setNum(0)
            return
        _floats(self.cap_line_coords.point, segs, 3)
        self.cap_line_set.numVertices.setNum(self.cap_line_count)
        self.cap_line_set.numVertices.setValues(0, self.cap_line_count, [2] * self.cap_line_count)
        self.cap_lines_switch.whichChild = coin.SO_SWITCH_ALL

    def cap_lines_shown(self):
        return self.cap_lines_switch.whichChild.getValue() != self.coin.SO_SWITCH_NONE

    def set_vectors(self, segments, colours=None, count=0):
        """The arrows on the cut: (s, 2, 3) segments with a colour each; `count` arrows."""
        np = _np()
        coin = self.coin
        segs = np.asarray(segments, dtype=float).reshape((-1, 2, 3))
        self.vector_segments = segs
        self.vector_count = int(count) if len(segs) else 0
        if not len(segs):
            self.vectors_switch.whichChild = coin.SO_SWITCH_NONE
            self.vector_lines.numVertices.setNum(0)
            return
        _floats(self.vector_coords.point, segs.reshape((-1, 3)), 3)
        self.vector_lines.numVertices.setNum(len(segs))
        self.vector_lines.numVertices.setValues(0, len(segs), [2] * len(segs))
        colours = colours if colours is not None else [(0.1, 0.1, 0.12)] * len(segs)
        _floats(self.vector_material.diffuseColor, colours, 3)
        self.vectors_switch.whichChild = coin.SO_SWITCH_ALL

    def vectors_shown(self):
        return self.vectors_switch.whichChild.getValue() != self.coin.SO_SWITCH_NONE

    def set_iso(self, triangles, colour=None, rest=None):
        """The iso-surface: triangles (k, 3, 3) as drawn, its colour, `rest` the same points on
        the unloaded part (Point Probes). Empty hides it."""
        np = _np()
        coin = self.coin
        tris = np.asarray(triangles, dtype=float).reshape((-1, 3))
        if not len(tris):
            self.iso_switch.whichChild = coin.SO_SWITCH_NONE
            self.iso_points = np.zeros((0, 3))
            self.iso_rest = np.zeros((0, 3))
            self.iso_faces.numVertices.setNum(0)
            return
        self.iso_points = tris
        self.iso_rest = (
            np.asarray(rest, dtype=float).reshape((-1, 3)) if rest is not None else tris.copy()
        )
        if colour is not None:
            self.iso_material.diffuseColor.setValue(*[float(c) for c in colour])
        _floats(self.iso_coords.point, tris, 3)
        count = len(tris) // 3
        self.iso_faces.numVertices.setNum(count)
        self.iso_faces.numVertices.setValues(0, count, [3] * count)
        self.iso_switch.whichChild = coin.SO_SWITCH_ALL

    def iso_shown(self):
        return self.iso_switch.whichChild.getValue() != self.coin.SO_SWITCH_NONE

    def iso_colour(self):
        return tuple(float(c) for c in self.iso_material.diffuseColor[0].getValue())

    def colour_of(self, position):
        """The colour a colour map position is drawn in (what the texture holds there)."""
        return core.map_colour(position)

    def node_positions(self):
        """{node index (of the whole mesh): colour map position} read back from the Coin
        texture coordinates (what is drawn)."""
        coords = self.texcoords.point.getValues()
        out = {}
        for k, node in enumerate(self.nodes.tolist()):
            s, t = coords[k][0], coords[k][1]
            out[node] = None if t > 0.5 else float(s)
        return out


# -- projecting 3D points onto the view ----------------------------------------------------------
def gl_widget_of(doc_name):
    """The OpenGL widget of the 3D view in front when it shows document `doc_name`."""
    try:
        gui = Gui.ActiveDocument
        if gui is None or gui.Document.Name != doc_name:
            return None
        area = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
        sub = area.activeSubWindow() if area is not None else None
        if sub is None:
            return None
        for widget in sub.findChildren(QtWidgets.QWidget):
            if widget.metaObject().className() == "QOpenGLWidget":
                return widget
    except Exception:
        return None
    return None


def overlay_parent(gl):
    """The widget the overlays live in: the 3D view widget that holds the OpenGL widget (a
    child of the OpenGL widget itself crashed Qt when it was grabbed or drawn off screen)."""
    try:
        parent = gl.parentWidget()
        return parent if parent is not None else gl
    except Exception:
        return gl


def in_parent(gl, x, y):
    """A point of the OpenGL widget in its overlay parent's coordinates."""
    parent = overlay_parent(gl)
    if parent is gl:
        return QtCore.QPoint(int(x), int(y))
    return gl.mapTo(parent, QtCore.QPoint(int(x), int(y)))


def project(view, gl, point):
    """Widget pixel (QPointF in `gl`) of a 3D point, or None."""
    try:
        x, y = view.getPointOnViewport(App.Vector(*point))
        ratio = gl.devicePixelRatioF()
        return QtCore.QPointF(x / ratio, gl.height() - y / ratio)
    except Exception:
        return None


def camera_key(view, gl):
    """What changes when the picture of the view moves (camera, size)."""
    try:
        cam = view.getCameraNode()
        p = cam.position.getValue()
        q = cam.orientation.getValue().getValue()
        h = 0.0
        for name in ("height", "heightAngle"):
            try:
                h = getattr(cam, name).getValue()
                break
            except Exception:
                continue
        return (
            round(p[0], 6),
            round(p[1], 6),
            round(p[2], 6),
            tuple(round(c, 6) for c in q),
            round(h, 6),
            gl.width(),
            gl.height(),
        )
    except Exception:
        return None


def ray(view, gl, pos):
    """(origin, direction) of the line of sight through widget pixel `pos` (QPoint)."""
    ratio = gl.devicePixelRatioF()
    x = int(round(pos.x() * ratio))
    y = int(round((gl.height() - pos.y()) * ratio))
    return ray_coin(view, x, y)


def ray_coin(view, x, y):
    """(origin, direction) through the Coin pixel (x, y) (origin bottom left)."""
    focal = App.Vector(*view.getPoint(int(x), int(y)))
    cam = view.getCameraNode()
    if view.getCameraType() == "Perspective":
        p = cam.position.getValue()
        origin = App.Vector(p[0], p[1], p[2])
        direction = focal - origin
    else:
        direction = App.Vector(*view.getViewDirection())
        origin = focal - direction * 1.0e6
    if direction.Length < 1e-12:
        direction = App.Vector(*view.getViewDirection())
    direction.normalize()
    return (origin.x, origin.y, origin.z), (direction.x, direction.y, direction.z)


# -- the overlay: min / max and probe tags ---------------------------------------------------------
class TagLayer(QtWidgets.QWidget):
    """Tags floating over the 3D view (not clickable: clicks reach the view under them): each
    a dot at a 3D point, a short line and a box with its text, like Fusion's min / max tags.
    tags: [{"point": (x, y, z), "text": str, "kind": "min" | "max" | "probe" | "point" (a Point
    Probe: a diamond), "colour": (r, g, b)}]; `placed` holds where each tag was last drawn (the
    scenarios read it)."""

    def __init__(self, gl, view):
        super().__init__(overlay_parent(gl))
        self.setObjectName("SciForgeSimTags")
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.gl = gl
        self.view = view
        self.tags = []
        self.placed = []
        self.boxes = []  # each tag's box as drawn last (the scenarios read it)
        self.setGeometry(self._area())
        self.show()
        self.raise_()

    def _area(self):
        """The OpenGL widget's rectangle in this layer's parent (tags are placed in the OpenGL
        widget's coordinates, so the layer covers it exactly)."""
        corner = in_parent(self.gl, 0, 0)
        return QtCore.QRect(corner.x(), corner.y(), self.gl.width(), self.gl.height())

    def set_tags(self, tags):
        self.tags = list(tags)
        self.relayout()

    def relayout(self):
        if not _alive(self.gl):
            return
        area = self._area()
        if self.geometry() != area:
            self.setGeometry(area)
        placed = []
        for tag in self.tags:
            pos = project(self.view, self.gl, tag["point"])
            placed.append(pos)
        self.placed = placed
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            font = painter.font()
            font.setPointSizeF(max(font.pointSizeF(), 9.0))
            painter.setFont(font)
            metrics = QtGui.QFontMetrics(font)
            self.boxes = self._layout(metrics)
            for tag, pos, rect in zip(self.tags, self.placed, self.boxes):
                if pos is None or rect is None:
                    continue
                self._paint_tag(painter, tag, pos, rect)
        except Exception as exc:
            warn("results tags: %s" % exc)
        finally:
            painter.end()

    @staticmethod
    def _offset(kind):
        """Where a tag's box goes from its point (pixels), by kind."""
        if kind == "min":
            return 16, 18
        if kind in ("probe", "point", "hover"):
            return 14, -20
        if kind == "reaction":
            return 18, 24
        return 16, -26

    def _layout(self, metrics):
        """Each tag's box: beside its point, moved down past the boxes before it when they
        would overlap (tags at nearby places stay readable)."""
        boxes = []
        for tag, pos in zip(self.tags, self.placed):
            if pos is None:
                boxes.append(None)
                continue
            dx, dy = self._offset(tag.get("kind", "probe"))
            width = metrics.horizontalAdvance(tag.get("text", "")) + 14
            height = metrics.height() + 6
            rect = QtCore.QRectF(pos.x() + dx, pos.y() + dy - height / 2.0, width, height)
            for _ in range(len(boxes) + 1):
                clash = [
                    b for b in boxes if b is not None and b.intersects(rect.adjusted(-2, -2, 2, 2))
                ]
                if not clash:
                    break
                rect.moveTop(max(b.bottom() for b in clash) + 3)
            boxes.append(rect)
        return boxes

    def _paint_tag(self, painter, tag, pos, rect):
        kind = tag.get("kind", "probe")
        text = tag.get("text", "")
        colour = QtGui.QColor.fromRgbF(
            *[min(max(c, 0.0), 1.0) for c in tag.get("colour", (1, 1, 1))]
        )
        painter.setPen(QtGui.QPen(QtGui.QColor(20, 22, 26), 1.6))
        painter.drawLine(pos, QtCore.QPointF(rect.left(), rect.center().y()))
        painter.setBrush(QtGui.QBrush(colour))
        if kind == "point":  # a Point Probe (inside the part): a diamond
            painter.setPen(QtGui.QPen(QtGui.QColor(245, 245, 245), 1.4))
            painter.drawPolygon(
                QtGui.QPolygonF(
                    [
                        QtCore.QPointF(pos.x(), pos.y() - 6),
                        QtCore.QPointF(pos.x() + 6, pos.y()),
                        QtCore.QPointF(pos.x(), pos.y() + 6),
                        QtCore.QPointF(pos.x() - 6, pos.y()),
                    ]
                )
            )
        else:
            painter.drawEllipse(pos, 4.5, 4.5)
        if kind == "probe":
            painter.setPen(QtGui.QPen(QtGui.QColor(245, 245, 245), 1.2))
            painter.drawLine(
                QtCore.QPointF(pos.x() - 7, pos.y()), QtCore.QPointF(pos.x() + 7, pos.y())
            )
            painter.drawLine(
                QtCore.QPointF(pos.x(), pos.y() - 7), QtCore.QPointF(pos.x(), pos.y() + 7)
            )
        if kind == "hover":  # the value under the mouse: a lighter box, not placed yet
            painter.setPen(QtGui.QPen(QtGui.QColor(160, 170, 185), 1.0, QtCore.Qt.DashLine))
            painter.setBrush(QtGui.QBrush(QtGui.QColor(43, 49, 59, 170)))
        else:
            painter.setPen(QtGui.QPen(QtGui.QColor(86, 96, 111), 1.0))
            painter.setBrush(QtGui.QBrush(QtGui.QColor(43, 49, 59, 235)))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QtGui.QColor(245, 245, 245))
        painter.drawText(rect, QtCore.Qt.AlignCenter, text)


# -- the legend ------------------------------------------------------------------------------------
LEGEND_STYLE = """
#SciForgeSimLegend { background: #3b4453; border: 1px solid #56606f; border-radius: 6px; }
#SciForgeSimLegend QLabel { color: #f5f5f5; background: transparent; }
#SciForgeSimLegend QLabel[role="dim"] { color: #c3cad4; }
#SciForgeSimLegend QLabel[role="warning"] { color: #ffcc66; }
#SciForgeSimLegend QComboBox { background: #2f3540; color: #f5f5f5; border: 1px solid #56606f;
    padding: 1px 4px; border-radius: 3px; }
#SciForgeSimLegend QToolButton, #SciForgeSimLegend QPushButton { background: #4a5568;
    color: #f5f5f5; border: 1px solid #56606f; border-radius: 3px; padding: 2px 6px; }
#SciForgeSimLegend QToolButton:hover, #SciForgeSimLegend QPushButton:hover { background: #56647a; }
"""


class ColourBar(QtWidgets.QWidget):
    """The legend's vertical colour bar with its values (top = high). Its two ends have handles
    (Fusion: drag the top or the bottom of the legend to narrow the range): dragging one and
    letting go sets the colours' range (`on_range(lo, hi)`, base unit); a double-click goes
    back to the result's own range (`on_reset()`). Not for the safety factor."""

    MARGIN = 8

    def __init__(self, parent=None, on_range=None, on_reset=None):
        super().__init__(parent)
        self.setObjectName("SciForgeSimColourBar")
        self.info = None
        self.on_range = on_range
        self.on_reset = on_reset
        self.dragging = None  # "hi" | "lo" while an end is dragged
        self.drag_y = None
        self.setMinimumHeight(190)
        self.setMinimumWidth(150)
        self.setMouseTracking(True)

    def set_info(self, info):
        self.info = info
        self.update()

    def draggable(self):
        info = self.info
        return (
            self.on_range is not None
            and bool(info)
            and info.get("result") != "safety"
            and not info.get("bands")
        )

    def _ends(self):
        return self.MARGIN, self.height() - self.MARGIN

    def end_at(self, y):
        """ "hi" or "lo" when the pixel row y is on one of the bar's handles, else None."""
        if not self.draggable():
            return None
        top, bottom = self._ends()
        if abs(y - top) <= 7:
            return "hi"
        if abs(y - bottom) <= 7:
            return "lo"
        return None

    def end_y(self, end):
        top, bottom = self._ends()
        return top if end == "hi" else bottom

    def fraction_at(self, y):
        top, bottom = self._ends()
        return (bottom - float(y)) / max(bottom - top, 1)

    def mousePressEvent(self, event):
        try:
            y = event.position().y() if hasattr(event, "position") else event.y()
            end = self.end_at(y)
            if end is not None and event.button() == QtCore.Qt.LeftButton:
                self.dragging, self.drag_y = end, y
                self.update()
                event.accept()
                return
        except Exception as exc:
            warn("results legend: %s" % exc)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        try:
            y = event.position().y() if hasattr(event, "position") else event.y()
            if self.dragging is not None:
                top, bottom = self._ends()
                self.drag_y = min(max(y, top), bottom)
                self.update()
            else:
                hot = self.end_at(y) is not None
                self.setCursor(QtCore.Qt.SizeVerCursor if hot else QtCore.Qt.ArrowCursor)
        except Exception as exc:
            warn("results legend: %s" % exc)

    def mouseReleaseEvent(self, event):
        try:
            end, self.dragging = self.dragging, None
            if end is not None and self.info and self.on_range is not None:
                y = event.position().y() if hasattr(event, "position") else event.y()
                top, bottom = self._ends()
                y = min(max(y, top), bottom)
                lo, hi = core.dragged_span(
                    self.info["lo"], self.info["hi"], end, self.fraction_at(y)
                )
                self.drag_y = None
                self.update()
                self.on_range(lo, hi)
                return
        except Exception as exc:
            warn("results legend: %s" % exc)
        self.drag_y = None

    def mouseDoubleClickEvent(self, event):
        try:
            if self.draggable() and self.info.get("custom") and self.on_reset is not None:
                self.on_reset()
                return
        except Exception as exc:
            warn("results legend: %s" % exc)
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, _event):
        info = self.info
        if not info:
            return
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            top, bottom = 8, self.height() - 8
            bar = QtCore.QRectF(4, top, 18, bottom - top)
            bands = info.get("bands")
            if bands:
                # the safety factor target bands, drawn where their values sit on the scale
                lower, upper = info["targets"]
                cap = info["hi"] or 1.0
                edges = [(cap, upper, "above"), (upper, lower, "meets"), (lower, 0.0, "below")]
                for hi_v, lo_v, state in edges:
                    y0 = bottom - (hi_v / cap) * (bottom - top)
                    y1 = bottom - (lo_v / cap) * (bottom - top)
                    colour = core.BAND_COLOURS[state]
                    painter.fillRect(
                        QtCore.QRectF(bar.left(), y0, bar.width(), y1 - y0),
                        QtGui.QColor.fromRgbF(*colour),
                    )
            else:
                steps = int(bar.height())
                for i in range(steps):
                    # the top of the bar is the high end of the scale (red, or blue for the
                    # safety factor, whose scale is reversed)
                    t = 1.0 - (i + 0.5) / steps
                    if info.get("reverse"):
                        t = 1.0 - t
                    colour = core.map_colour(t, info.get("banded"))
                    painter.fillRect(
                        QtCore.QRectF(bar.left(), bar.top() + i, bar.width(), 1.2),
                        QtGui.QColor.fromRgbF(*colour),
                    )
            painter.setPen(QtGui.QPen(QtGui.QColor("#56606f"), 1))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(bar)
            if self.draggable():  # the two handles: small arrows at the ends of the bar
                for end in ("hi", "lo"):
                    y = self.end_y(end)
                    if self.dragging == end and self.drag_y is not None:
                        y = self.drag_y
                        painter.setPen(QtGui.QPen(QtGui.QColor("#f5f5f5"), 1, QtCore.Qt.DashLine))
                        painter.drawLine(
                            QtCore.QPointF(bar.left(), y), QtCore.QPointF(bar.right(), y)
                        )
                    painter.setPen(QtGui.QPen(QtGui.QColor("#1f2329"), 1))
                    painter.setBrush(QtGui.QBrush(QtGui.QColor("#f5f5f5")))
                    painter.drawPolygon(
                        QtGui.QPolygonF(
                            [
                                QtCore.QPointF(0.0, y - 5.0),
                                QtCore.QPointF(6.0, y),
                                QtCore.QPointF(0.0, y + 5.0),
                            ]
                        )
                    )
                painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QColor(self.palette().color(QtGui.QPalette.WindowText)))
            text_colour = QtGui.QColor("#f5f5f5")
            try:
                from . import theme

                if theme.is_light():
                    text_colour = QtGui.QColor("#1f2329")
            except Exception:
                pass
            painter.setPen(text_colour)
            metrics = painter.fontMetrics()
            for _value, text, pos in info.get("ticks", []):
                y = bottom - pos * (bottom - top)
                painter.drawLine(QtCore.QPointF(bar.right(), y), QtCore.QPointF(bar.right() + 4, y))
                label = text + (" " + info["unit"] if info.get("unit") else "")
                painter.drawText(QtCore.QPointF(bar.right() + 8, y + metrics.ascent() / 2.5), label)
        except Exception as exc:
            warn("results legend: %s" % exc)
        finally:
            painter.end()


class Legend(QtWidgets.QFrame):
    """The legend floating at the top left of the 3D view: the result (Fusion's type and
    component drop-downs), the unit, the colour bar with its values, the min and the max, the
    Results Details button, the deformation drawn, and the out-of-date warning with Solve."""

    def __init__(self, gl, callbacks):
        super().__init__(overlay_parent(gl))
        self.setObjectName("SciForgeSimLegend")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.gl = gl
        self.callbacks = callbacks
        self._filling = False
        self.setStyleSheet(LEGEND_STYLE)
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(8, 6, 8, 8)
        box.setSpacing(4)
        self.study_label = QtWidgets.QLabel("")
        self.study_label.setProperty("role", "dim")
        box.addWidget(self.study_label)
        row = QtWidgets.QHBoxLayout()
        self.group_box = QtWidgets.QComboBox()
        self.group_box.setObjectName("SciForgeSimResultGroup")
        for key, name in core.groups():
            self.group_box.addItem(name, key)
        self.group_box.currentIndexChanged.connect(self._group_chosen)
        row.addWidget(self.group_box, 1)
        self.details_button = QtWidgets.QToolButton()
        self.details_button.setObjectName("SciForgeSimDetailsButton")
        self.details_button.setText("i")
        self.details_button.setToolTip("Results Details: what the results mean")
        self.details_button.clicked.connect(lambda: self._call("details"))
        row.addWidget(self.details_button)
        # Fusion's legend options: smooth colours or colour bands
        self.options_button = QtWidgets.QToolButton()
        self.options_button.setObjectName("SciForgeSimLegendOptions")
        self.options_button.setText("...")
        self.options_button.setToolTip("Legend options")
        self.options_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(self.options_button)
        group = QtGui.QActionGroup(menu)
        group.setExclusive(True)
        self.smooth_action = menu.addAction("Smooth Colours")
        self.bands_action = menu.addAction("Colour Bands")
        for action in (self.smooth_action, self.bands_action):
            action.setCheckable(True)
            group.addAction(action)
        self.smooth_action.setChecked(True)
        self.smooth_action.triggered.connect(lambda: self._call("banded", False))
        self.bands_action.triggered.connect(lambda: self._call("banded", True))
        menu.addSeparator()
        self.range_action = menu.addAction("Legend Min/Max...")
        self.range_action.triggered.connect(lambda: self._call("range"))
        self.grey_action = menu.addAction("Grey Outside the Range")
        self.grey_action.setObjectName("SciForgeSimLegendGrey")
        self.grey_action.setCheckable(True)
        self.grey_action.setToolTip(
            "Values beyond the legend's range drawn grey instead of in the end colours"
        )
        self.grey_action.toggled.connect(lambda on: self._call("grey", on))
        self.options_button.setMenu(menu)
        row.addWidget(self.options_button)
        box.addLayout(row)
        row2 = QtWidgets.QHBoxLayout()
        self.part_box = QtWidgets.QComboBox()
        self.part_box.setObjectName("SciForgeSimResultComponent")
        self.part_box.currentIndexChanged.connect(self._part_chosen)
        row2.addWidget(self.part_box, 1)
        self.unit_box = QtWidgets.QComboBox()
        self.unit_box.setObjectName("SciForgeSimResultUnit")
        self.unit_box.currentIndexChanged.connect(self._unit_chosen)
        row2.addWidget(self.unit_box)
        box.addLayout(row2)
        self.max_label = QtWidgets.QLabel("")
        self.max_label.setObjectName("SciForgeSimLegendMax")
        box.addWidget(self.max_label)
        self.bar = ColourBar(  # (Compare has no range: no handles there)
            on_range=(lambda lo, hi: self._call("span", lo, hi)) if "span" in callbacks else None,
            on_reset=(lambda: self._call("span_reset")) if "span" in callbacks else None,
        )
        box.addWidget(self.bar)
        self.min_label = QtWidgets.QLabel("")
        self.min_label.setObjectName("SciForgeSimLegendMin")
        box.addWidget(self.min_label)
        self.range_label = QtWidgets.QLabel("")
        self.range_label.setObjectName("SciForgeSimLegendRange")
        self.range_label.setProperty("role", "dim")
        self.range_label.setWordWrap(True)
        box.addWidget(self.range_label)
        self.verdict_label = QtWidgets.QLabel("")
        self.verdict_label.setObjectName("SciForgeSimLegendVerdict")
        self.verdict_label.setWordWrap(True)
        box.addWidget(self.verdict_label)
        self.deform_label = QtWidgets.QLabel("")
        self.deform_label.setProperty("role", "dim")
        self.deform_label.setWordWrap(True)
        box.addWidget(self.deform_label)
        self.warning = QtWidgets.QLabel(core.OUT_OF_DATE)
        self.warning.setObjectName("SciForgeSimOutOfDate")
        self.warning.setProperty("role", "warning")
        self.warning.setWordWrap(True)
        box.addWidget(self.warning)
        self.compare_button = QtWidgets.QPushButton("Finish Compare")
        self.compare_button.setObjectName("SciForgeSimFinishCompare")
        self.compare_button.clicked.connect(lambda: self._call("finish_compare"))
        self.compare_button.hide()
        box.addWidget(self.compare_button)
        self.solve_button = QtWidgets.QPushButton("Solve Again")
        self.solve_button.setObjectName("SciForgeSimSolveAgain")
        self.solve_button.clicked.connect(lambda: self._call("solve"))
        box.addWidget(self.solve_button)
        self.warning.hide()
        self.solve_button.hide()
        self.setFixedWidth(232)
        self.info = None
        gl.installEventFilter(self)
        self.show()
        self.place()

    def _call(self, name, *args):
        try:
            fn = self.callbacks.get(name)
            if fn is not None:
                fn(*args)
        except Exception as exc:
            warn("results legend: %s" % exc)

    def eventFilter(self, obj, event):
        try:
            if obj is self.gl and event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
                QtCore.QTimer.singleShot(0, self.place)
        except Exception:
            pass
        return False

    def place(self):
        if not _alive(self) or not _alive(self.gl):
            return
        self.adjustSize()
        self.move(in_parent(self.gl, 12, 12))
        self.raise_()

    def fill(self, info, study_label, out_of_date, deformation_text):
        """Show a legend (simulation_results_core.legend())."""
        self._filling = True
        try:
            self.info = info
            group = core.group_of(info["result"])
            i = self.group_box.findData(group)
            if i >= 0 and i != self.group_box.currentIndex():
                self.group_box.setCurrentIndex(i)
            parts = core.components(group)
            self.part_box.clear()
            for key, name in parts:
                self.part_box.addItem(name, key)
            self.part_box.setCurrentIndex(max(0, self.part_box.findData(info["result"])))
            self.part_box.setVisible(len(parts) > 1)
            units = core.units_for(info["result"])
            self.unit_box.clear()
            for unit in units:
                self.unit_box.addItem(unit, unit)
            self.unit_box.setCurrentIndex(max(0, self.unit_box.findData(info["unit"])))
            self.unit_box.setVisible(units != [""])
            self.bands_action.setChecked(bool(info.get("banded")))
            self.smooth_action.setChecked(not info.get("banded"))
            self.max_label.setText("Max: %s" % info["max_text"])
            self.min_label.setText("Min: %s" % info["min_text"])
            verdict = info.get("verdict")
            self.verdict_label.setVisible(bool(verdict))
            if verdict:
                state, text = verdict
                colour = {"below": "#ff8a80", "meets": "#ffd666", "above": "#8cc4ff"}.get(
                    state, "#c3cad4"
                )
                try:
                    from . import theme

                    if theme.is_light():  # (darker on the light look's white panel)
                        colour = {"below": "#c62828", "meets": "#9a6b00", "above": "#1f6fbf"}.get(
                            state, "#5b6573"
                        )
                except Exception:
                    pass
                self.verdict_label.setText(text)
                self.verdict_label.setStyleSheet("QLabel { color: %s; }" % colour)
            self.range_label.setText(info.get("span_text", ""))
            self.range_label.setVisible(bool(info.get("custom")))
            self.range_action.setEnabled(info["result"] != "safety")
            self.grey_action.blockSignals(True)
            self.grey_action.setChecked(bool(info.get("grey")))
            self.grey_action.setEnabled(info["result"] != "safety")
            self.grey_action.blockSignals(False)
            self.bar.set_info(info)
            self.study_label.setText(study_label)
            self.deform_label.setText(deformation_text)
            self.warning.setVisible(bool(out_of_date))
            self.solve_button.setVisible(bool(out_of_date))
        finally:
            self._filling = False
        self.place()

    def _group_chosen(self, _index):
        if self._filling:
            return
        group = self.group_box.currentData()
        parts = core.components(group)
        if parts:
            self._call("result", parts[0][0])

    def _part_chosen(self, _index):
        if self._filling:
            return
        key = self.part_box.currentData()
        if key:
            self._call("result", key)

    def _unit_chosen(self, _index):
        if self._filling:
            return
        unit = self.unit_box.currentData()
        if unit is not None:
            self._call("unit", unit)

    def remove(self):
        try:
            if _alive(self.gl):
                self.gl.removeEventFilter(self)
        except Exception:
            pass
        try:
            self.hide()
            self.setParent(None)
            self.deleteLater()
        except RuntimeError:
            pass


# -- the animation bar ----------------------------------------------------------------------------
BAR_STYLE = """
#SciForgeSimAnimation { background: #3b4453; border: 1px solid #56606f; border-radius: 6px; }
#SciForgeSimAnimation QLabel { color: #f5f5f5; background: transparent; }
#SciForgeSimAnimation QComboBox { background: #2f3540; color: #f5f5f5; border: 1px solid #56606f;
    padding: 1px 4px; border-radius: 3px; }
#SciForgeSimAnimation QToolButton { background: #4a5568; color: #f5f5f5; border: 1px solid #56606f;
    border-radius: 3px; padding: 2px 8px; }
#SciForgeSimAnimation QToolButton:hover { background: #56647a; }
"""


class AnimationBar(QtWidgets.QFrame):
    """Play / Stop, speed, number of steps and play mode, at the bottom left of the 3D view (the
    newer Fusion viewer puts its animation bar at the bottom of the canvas)."""

    def __init__(self, gl, callbacks, speed=1.0, frames=20, mode="loop"):
        super().__init__(overlay_parent(gl))
        self.setObjectName("SciForgeSimAnimation")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet(BAR_STYLE)
        self.gl = gl
        self.callbacks = callbacks
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(6)
        title = QtWidgets.QLabel("Animate")
        row.addWidget(title)
        self.play_button = QtWidgets.QToolButton()
        self.play_button.setObjectName("SciForgeSimPlay")
        self.play_button.setText("Stop")
        self.play_button.clicked.connect(lambda: self._call("toggle"))
        row.addWidget(self.play_button)
        self.speed_box = QtWidgets.QComboBox()
        self.speed_box.setObjectName("SciForgeSimSpeed")
        for s in core.ANIMATION_SPEEDS:
            self.speed_box.addItem("%sx" % core.fmt(s), s)
        self.speed_box.setCurrentIndex(max(0, self.speed_box.findData(speed)))
        self.speed_box.currentIndexChanged.connect(
            lambda _i: self._call("speed", self.speed_box.currentData())
        )
        row.addWidget(self.speed_box)
        self.frames_box = QtWidgets.QComboBox()
        self.frames_box.setObjectName("SciForgeSimFrames")
        for f in core.ANIMATION_FRAMES:
            self.frames_box.addItem("%d steps" % f, f)
        self.frames_box.setCurrentIndex(max(0, self.frames_box.findData(frames)))
        self.frames_box.currentIndexChanged.connect(
            lambda _i: self._call("frames", self.frames_box.currentData())
        )
        row.addWidget(self.frames_box)
        self.mode_box = QtWidgets.QComboBox()
        self.mode_box.setObjectName("SciForgeSimPlayMode")
        for key, name in core.ANIMATION_MODES:
            self.mode_box.addItem(name, key)
        self.mode_box.setCurrentIndex(max(0, self.mode_box.findData(mode)))
        self.mode_box.currentIndexChanged.connect(
            lambda _i: self._call("mode", self.mode_box.currentData())
        )
        row.addWidget(self.mode_box)
        save = QtWidgets.QToolButton()
        save.setObjectName("SciForgeSimAnimationSave")
        save.setText("Save...")
        save.setToolTip("Save the animation as an animated picture (GIF or WebP)")
        save.clicked.connect(lambda: self._call("save"))
        row.addWidget(save)
        close = QtWidgets.QToolButton()
        close.setObjectName("SciForgeSimAnimationClose")
        close.setText("Close")
        close.clicked.connect(lambda: self._call("close"))
        row.addWidget(close)
        gl.installEventFilter(self)
        self.show()
        self.place()

    def _call(self, name, *args):
        try:
            fn = self.callbacks.get(name)
            if fn is not None:
                fn(*args)
        except Exception as exc:
            warn("results animation: %s" % exc)

    def set_playing(self, playing):
        self.play_button.setText("Stop" if playing else "Play")

    def eventFilter(self, obj, event):
        try:
            if obj is self.gl and event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
                QtCore.QTimer.singleShot(0, self.place)
        except Exception:
            pass
        return False

    def place(self):
        if not _alive(self) or not _alive(self.gl):
            return
        self.adjustSize()
        self.move(in_parent(self.gl, 12, max(0, self.gl.height() - self.height() - 64)))
        self.raise_()

    def remove(self):
        try:
            if _alive(self.gl):
                self.gl.removeEventFilter(self)
        except Exception:
            pass
        try:
            self.hide()
            self.setParent(None)
            self.deleteLater()
        except RuntimeError:
            pass
