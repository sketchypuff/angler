# encoding: utf-8

###########################################################################################################
#
#	Angler — Reporter Plugin
#
#	Shows the angle (0–180° from horizontal) of selected line segments,
#	BCP handles, and the handles of selected nodes in the Edit View.
#	Click a badge (or right-click › Set Angle…) to type a new angle.
#
###########################################################################################################

from __future__ import division, print_function, unicode_literals
import traceback
import objc
from collections import namedtuple
from math import atan2, cos, degrees, hypot, isinf, isnan, radians, sin
from GlyphsApp import Glyphs, OFFCURVE, LINE
from GlyphsApp.plugins import ReporterPlugin
from AppKit import (
	NSAttributedString,
	NSBezierPath,
	NSColor,
	NSEvent,
	NSEventMaskLeftMouseDown,
	NSEventMaskLeftMouseUp,
	NSEventTypeLeftMouseUp,
	NSEventModifierFlagCommand,
	NSEventModifierFlagControl,
	NSEventModifierFlagOption,
	NSEventModifierFlagShift,
	NSFont,
	NSFontAttributeName,
	NSForegroundColorAttributeName,
	NSMakePoint,
	NSMakeRect,
	NSMenuItem,
	NSMouseInRect,
	NSObject,
	NSTextAlignmentCenter,
	NSTextField,
)

# All sizes are in screen points and get divided by the zoom scale.
FONT_SIZE = 10.0
BADGE_PAD_X = 4.0
BADGE_PAD_Y = 2.0
BADGE_GAP = 4.0
ARC_RADIUS = 16.0
TICK_LENGTH = 22.0
LINE_WIDTH = 1.0

# Size of the inline editor, in screen points.
EDITOR_MIN_WIDTH = 56.0
EDITOR_MIN_HEIGHT = 20.0

# Prints what the click/editor code is doing to the Macro Panel.
DEBUG = False

# Angles within this many degrees of an axis (but not on it) get flagged.
NEAR_AXIS_TOLERANCE = 0.5
ON_AXIS_EPSILON = 1e-6

# Clicks with these modifiers go to Glyphs, so shift-click selection still works.
PASSTHROUGH_MODIFIERS = (
	NSEventModifierFlagShift
	| NSEventModifierFlagCommand
	| NSEventModifierFlagOption
	| NSEventModifierFlagControl
)


def log(*args):
	if DEBUG:
		print("Angler:", *args)


def rgba(r, g, b, a):
	return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)


COLOR_NORMAL = rgba(0.15, 0.15, 0.15, 0.85)
COLOR_NEAR_AXIS = rgba(1.0, 0.5, 0.0, 0.95)
COLOR_ON_AXIS = rgba(0.15, 0.6, 0.3, 0.9)
COLOR_TEXT = rgba(1.0, 1.0, 1.0, 1.0)

# rect is (x, y, w, h) in layer coordinates; anchor/mover are (path_index, node_index).
Badge = namedtuple("Badge", "rect anchor mover angle")


def angle_of(a, b):
	"""Direction-agnostic angle of the line a→b, in [0, 180)."""
	return degrees(atan2(b[1] - a[1], b[0] - a[0])) % 180.0


def axis_deviation(angle):
	return min(angle, abs(angle - 90.0), 180.0 - angle)


def neighbor_index(count, closed, i, step):
	j = i + step
	if 0 <= j < count:
		return j
	return j % count if closed and count > 1 else None


def parse_angle(text):
	try:
		value = float(text.replace("°", "").strip())
	except (AttributeError, ValueError):
		return None
	if isnan(value) or isinf(value):
		return None
	return value


def rect_contains(rect, point):
	x, y, w, h = rect
	return x <= point[0] <= x + w and y <= point[1] <= y + h


def selector_name(selector):
	if isinstance(selector, bytes):
		return selector.decode("ascii")
	return str(selector)


class AnglerEditorDelegate(NSObject):
	"""Routes the inline text field's keys back to the plugin."""

	@objc.typedSelector(b"Z@:@@:")
	def control_textView_doCommandBySelector_(self, control, textView, selector):
		name = selector_name(selector)
		if name == "insertNewline:":
			self.plugin.commit_editor()
			return True
		if name == "cancelOperation:":
			self.plugin.close_editor(refocus=True)
			return True
		return False

	def controlTextDidEndEditing_(self, notification):
		# Glyphs can pull focus back right after the field opens, so this
		# doesn't close the editor; a click outside it does (handle_mouse_down).
		log("editor lost focus")


class Angler(ReporterPlugin):

	@objc.python_method
	def settings(self):
		self.menuName = Glyphs.localize({
			'en': 'Angler',
		})

	@objc.python_method
	def start(self):
		self.badges = []
		self.badge_layer = None
		self.editor = None
		self.editor_delegate = None
		self.editor_target = None
		self.pending_badge = None
		self.swallow_mouse_up = False
		self.mouse_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
			NSEventMaskLeftMouseDown | NSEventMaskLeftMouseUp, self.handle_mouse_event
		)
		log("started, monitor installed:", self.mouse_monitor is not None)

	@objc.python_method
	def foreground(self, layer):
		scale = self.getScale()
		if not scale:
			return
		badges = []
		for anchor, mover in self.collect_pairs(layer):
			a = self.node_at(layer, anchor)
			b = self.node_at(layer, mover)
			rect, angle = self.draw_measurement((a.x, a.y), (b.x, b.y), scale)
			badges.append(Badge(rect, anchor, mover, angle))
		self.badges = badges
		self.badge_layer = layer

	@objc.python_method
	def node_at(self, layer, ref):
		path_index, node_index = ref
		try:
			return layer.paths[path_index].nodes[node_index]
		except (IndexError, TypeError):
			return None

	@objc.python_method
	def collect_pairs(self, layer):
		"""Returns a list of (anchor, mover) node refs to measure.

		Each ref is (path_index, node_index). The anchor stays put when the
		angle is edited, and the mover rotates around it.
		"""
		pairs = []
		seen = set()
		selected = []

		def add(path_index, i, j, nodes):
			key = frozenset(((path_index, i), (path_index, j)))
			if i == j or key in seen:
				return
			seen.add(key)
			a, b = nodes[i], nodes[j]
			if hypot(b.x - a.x, b.y - a.y) > 0:
				pairs.append(((path_index, i), (path_index, j)))

		for path_index, path in enumerate(layer.paths):
			nodes = list(path.nodes)
			count = len(nodes)
			closed = path.closed

			for i, node in enumerate(nodes):
				if not node.selected:
					continue
				selected.append((path_index, i, node))
				prev_i = neighbor_index(count, closed, i, -1)
				next_i = neighbor_index(count, closed, i, 1)

				if node.type == OFFCURVE:
					# A handle belongs to the on-curve node next to it.
					if prev_i is not None and nodes[prev_i].type != OFFCURVE:
						add(path_index, prev_i, i, nodes)
					elif next_i is not None and nodes[next_i].type != OFFCURVE:
						add(path_index, next_i, i, nodes)
					continue

				# On-curve node: show both of its handles.
				for j in (prev_i, next_i):
					if j is not None and nodes[j].type == OFFCURVE:
						add(path_index, i, j, nodes)

				# Straight segment ending at this node, if both ends are selected.
				if node.type == LINE and prev_i is not None:
					prev = nodes[prev_i]
					if prev.type != OFFCURVE and prev.selected:
						add(path_index, prev_i, i, nodes)

		# Exactly two selected points that aren't already related.
		if len(selected) == 2:
			(pa, ia, a), (pb, ib, b) = selected
			key = frozenset(((pa, ia), (pb, ib)))
			if key not in seen and hypot(b.x - a.x, b.y - a.y) > 0:
				pairs.append(((pa, ia), (pb, ib)))

		return pairs

	@objc.python_method
	def draw_measurement(self, anchor, other, scale):
		"""Draws the arc and badge; returns (badge_rect, angle)."""
		dx = other[0] - anchor[0]
		dy = other[1] - anchor[1]
		length = hypot(dx, dy)
		raw = degrees(atan2(dy, dx))
		angle = raw % 180.0
		deviation = axis_deviation(angle)

		if deviation < ON_AXIS_EPSILON:
			color = COLOR_ON_AXIS
		elif deviation <= NEAR_AXIS_TOLERANCE:
			color = COLOR_NEAR_AXIS
		else:
			color = COLOR_NORMAL

		self.draw_arc(anchor, raw, angle, length, color, scale)
		rect = self.draw_badge(anchor, other, dx, dy, length, angle, color, scale)
		return rect, angle

	@objc.python_method
	def draw_arc(self, anchor, raw, angle, length, color, scale):
		# Measure from the horizontal ray on the same side as the line,
		# so the arc always sweeps counterclockwise by `angle`.
		base = raw - angle
		radius = min(ARC_RADIUS / scale, length * 0.4)
		tick = TICK_LENGTH / scale
		center = NSMakePoint(anchor[0], anchor[1])

		path = NSBezierPath.bezierPath()
		path.setLineWidth_(LINE_WIDTH / scale)
		direction = 1.0 if abs(base) < 90.0 else -1.0
		path.moveToPoint_(center)
		path.lineToPoint_(NSMakePoint(anchor[0] + direction * tick, anchor[1]))
		if angle > 0:
			path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
				center, radius, base, raw, False
			)
		color.set()
		path.stroke()

	@objc.python_method
	def draw_badge(self, anchor, other, dx, dy, length, angle, color, scale):
		"""Draws the angle badge; returns its rect as (x, y, w, h) in layer coordinates."""
		shown = round(angle, 1) % 180.0
		text = "%.1f°" % shown
		attrs = {
			NSFontAttributeName: NSFont.monospacedDigitSystemFontOfSize_weight_(FONT_SIZE / scale, 0.0),
			NSForegroundColorAttributeName: COLOR_TEXT,
		}
		label = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
		size = label.size()
		pad_x = BADGE_PAD_X / scale
		pad_y = BADGE_PAD_Y / scale
		width = size.width + 2 * pad_x
		height = size.height + 2 * pad_y

		# Push the badge off the line along its normal so it doesn't hide the line.
		nx, ny = -dy / length, dx / length
		if ny < 0 or (ny == 0 and nx < 0):
			nx, ny = -nx, -ny
		offset = abs(nx) * width / 2 + abs(ny) * height / 2 + BADGE_GAP / scale
		cx = (anchor[0] + other[0]) / 2 + nx * offset
		cy = (anchor[1] + other[1]) / 2 + ny * offset

		rect = NSMakeRect(cx - width / 2, cy - height / 2, width, height)
		radius = height / 2
		color.set()
		NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius).fill()
		label.drawAtPoint_(NSMakePoint(cx - size.width / 2, cy - size.height / 2))
		return (cx - width / 2, cy - height / 2, width, height)

	# ------------------------------------------------------------------
	# Editing: click a badge

	@objc.python_method
	def graphic_view(self):
		controller = self.controller
		if controller:
			return controller.graphicView()
		try:
			return Glyphs.font.currentTab.graphicView()
		except AttributeError:
			return None

	@objc.python_method
	def is_active(self):
		try:
			return self in Glyphs.activeReporters
		except Exception:
			return False

	@objc.python_method
	def handle_mouse_event(self, event):
		try:
			if event.type() == NSEventTypeLeftMouseUp:
				if self.swallow_mouse_up:
					self.swallow_mouse_up = False
					return None
				return event
			return self.handle_mouse_down(event)
		except Exception:
			print(traceback.format_exc())
		return event

	@objc.python_method
	def handle_mouse_down(self, event):
		view = self.graphic_view()
		if view is None or event.window() is None or event.window() != view.window():
			return event
		view_point = view.convertPoint_fromView_(event.locationInWindow(), None)

		if self.editor is not None:
			if NSMouseInRect(view_point, self.editor.frame(), view.isFlipped()):
				return event
			log("click outside editor, cancelling")
			self.close_editor(refocus=False)

		if event.modifierFlags() & PASSTHROUGH_MODIFIERS or not self.badges:
			return event
		if not self.is_active():
			log("click ignored: reporter not in Glyphs.activeReporters")
			return event
		if view.activeLayer() != self.badge_layer:
			log("click ignored: active layer differs from drawn layer")
			return event
		point = self.view_to_layer(view, view_point)
		for badge in reversed(self.badges):
			if rect_contains(badge.rect, point):
				log("badge hit at", point)
				self.swallow_mouse_up = True
				self.request_editor(badge)
				return None
		log("click at", point, "missed badges", [b.rect for b in self.badges])
		return event

	@objc.python_method
	def view_to_layer(self, view, view_point):
		origin = view.activePosition()
		scale = view.scale()
		dy = origin.y - view_point.y if view.isFlipped() else view_point.y - origin.y
		return ((view_point.x - origin.x) / scale, dy / scale)

	@objc.python_method
	def layer_rect_to_view(self, view, rect):
		origin = view.activePosition()
		scale = view.scale()
		x, y, w, h = rect
		if view.isFlipped():
			view_y = origin.y - (y + h) * scale
		else:
			view_y = origin.y + y * scale
		return (origin.x + x * scale, view_y, w * scale, h * scale)

	@objc.python_method
	def request_editor(self, badge):
		# Open on the next run-loop pass, after the click or menu has finished
		# and Glyphs is done moving focus around.
		self.pending_badge = badge
		self.performSelector_withObject_afterDelay_("openPendingEditor:", None, 0.0)

	def openPendingEditor_(self, _):
		badge = self.pending_badge
		self.pending_badge = None
		if badge is None:
			return
		try:
			self.open_editor(badge)
		except Exception:
			print(traceback.format_exc())

	@objc.python_method
	def open_editor(self, badge):
		self.close_editor()
		view = self.graphic_view()
		layer = self.badge_layer
		if view is None or layer is None:
			log("can't open editor: view", view, "layer", layer)
			return

		x, y, w, h = self.layer_rect_to_view(view, badge.rect)
		width = max(w, EDITOR_MIN_WIDTH)
		height = max(h, EDITOR_MIN_HEIGHT)
		frame = NSMakeRect(x + w / 2 - width / 2, y + h / 2 - height / 2, width, height)

		field = NSTextField.alloc().initWithFrame_(frame)
		field.setStringValue_("%.1f" % (round(badge.angle, 1) % 180.0))
		field.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(FONT_SIZE + 1, 0.0))
		field.setAlignment_(NSTextAlignmentCenter)
		field.setBezeled_(True)
		field.setEditable_(True)

		delegate = AnglerEditorDelegate.alloc().init()
		delegate.plugin = self
		field.setDelegate_(delegate)

		self.editor = field
		self.editor_delegate = delegate
		self.editor_target = (layer, badge)

		view.addSubview_(field)
		view.window().makeFirstResponder_(field)
		field.selectText_(None)
		log("editor opened at", frame, "in", view.className(), "flipped:", view.isFlipped())

	@objc.python_method
	def commit_editor(self):
		field = self.editor
		target = self.editor_target
		if field is None or target is None:
			return
		text = field.stringValue()
		value = parse_angle(text)
		self.close_editor(refocus=True)
		log("commit", repr(text), "->", value)
		if value is None:
			return
		layer, badge = target
		try:
			self.set_angle(layer, badge.anchor, badge.mover, value)
		except Exception:
			print(traceback.format_exc())

	@objc.python_method
	def close_editor(self, refocus=False):
		field = self.editor
		if field is None:
			return
		# Clear state first: removing the field ends editing, which calls back here.
		self.editor = None
		self.editor_target = None
		field.setDelegate_(None)
		view = field.superview()
		field.removeFromSuperview()
		self.editor_delegate = None
		# Only hand focus back on Enter/Esc; on a click elsewhere the window is already moving it.
		if refocus and view is not None and view.window() is not None:
			view.window().makeFirstResponder_(view)

	# ------------------------------------------------------------------
	# Editing: right-click menu

	@objc.python_method
	def conditionalContextMenus(self):
		if not self.badges:
			return []
		items = []
		for index, badge in enumerate(self.badges):
			title = "Set Angle (%.1f°)…" % (round(badge.angle, 1) % 180.0)
			item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "setAngleFromMenu:", "")
			item.setTag_(index)
			items.append({"menu": item})
		return items

	def setAngleFromMenu_(self, sender):
		try:
			index = sender.tag()
			log("menu item chosen, index", index)
			if 0 <= index < len(self.badges):
				self.request_editor(self.badges[index])
		except Exception:
			print(traceback.format_exc())

	# ------------------------------------------------------------------
	# Geometry

	@objc.python_method
	def set_angle(self, layer, anchor_ref, mover_ref, target):
		anchor = self.node_at(layer, anchor_ref)
		mover = self.node_at(layer, mover_ref)
		if anchor is None or mover is None:
			return
		dx = mover.x - anchor.x
		dy = mover.y - anchor.y
		length = hypot(dx, dy)
		if length == 0:
			return

		# The typed angle is direction-agnostic; keep the side closest to now.
		current = degrees(atan2(dy, dx))
		base = target % 180.0
		direction = min(
			(base - 180.0, base, base + 180.0),
			key=lambda c: abs((c - current + 180.0) % 360.0 - 180.0),
		)
		snap = self.snapper(layer)
		new_x = snap(anchor.x + length * cos(radians(direction)))
		new_y = snap(anchor.y + length * sin(radians(direction)))

		path_index, mover_index = mover_ref
		path = layer.paths[path_index]
		nodes = list(path.nodes)
		count = len(nodes)
		closed = path.closed

		glyph = layer.parent
		glyph.beginUndo()
		try:
			shift_x = new_x - mover.x
			shift_y = new_y - mover.y
			mover.position = NSMakePoint(new_x, new_y)

			if mover.type == OFFCURVE:
				parent = self.handle_parent(nodes, closed, mover_index)
				if parent is not None:
					self.realign_smooth(nodes, closed, parent, mover_index, snap)
			else:
				# Moving an on-curve node takes its handles along, like dragging it.
				for step in (-1, 1):
					j = neighbor_index(count, closed, mover_index, step)
					if j is not None and nodes[j].type == OFFCURVE and (path_index, j) != anchor_ref:
						handle = nodes[j]
						handle.position = NSMakePoint(handle.x + shift_x, handle.y + shift_y)
				# Segment between two on-curve neighbors: keep smooth handles at both ends in line.
				anchor_path, anchor_index = anchor_ref
				if anchor_path == path_index and anchor.type != OFFCURVE and anchor_index in (
					neighbor_index(count, closed, mover_index, -1),
					neighbor_index(count, closed, mover_index, 1),
				):
					self.realign_smooth(nodes, closed, mover_index, anchor_index, snap)
					self.realign_smooth(nodes, closed, anchor_index, mover_index, snap)
		finally:
			glyph.endUndo()
		Glyphs.redraw()

	@objc.python_method
	def handle_parent(self, nodes, closed, i):
		"""The on-curve node a handle belongs to, or None."""
		count = len(nodes)
		for step in (-1, 1):
			j = neighbor_index(count, closed, i, step)
			if j is not None and nodes[j].type != OFFCURVE:
				return j
		return None

	@objc.python_method
	def realign_smooth(self, nodes, closed, i, via, snap):
		"""If node i is smooth, rotate its handle opposite `via` to stay collinear.

		The handle keeps its own length. If the opposite side is a line,
		nothing moves.
		"""
		node = nodes[i]
		if node.type == OFFCURVE or not node.smooth:
			return
		count = len(nodes)
		prev_i = neighbor_index(count, closed, i, -1)
		next_i = neighbor_index(count, closed, i, 1)
		if via == prev_i:
			other = next_i
		elif via == next_i:
			other = prev_i
		else:
			return
		if other is None or other == via or nodes[other].type != OFFCURVE:
			return
		dx = node.x - nodes[via].x
		dy = node.y - nodes[via].y
		dist = hypot(dx, dy)
		if dist == 0:
			return
		handle = nodes[other]
		handle_length = hypot(handle.x - node.x, handle.y - node.y)
		handle.position = NSMakePoint(
			snap(node.x + dx / dist * handle_length),
			snap(node.y + dy / dist * handle_length),
		)

	@objc.python_method
	def snapper(self, layer):
		font = layer.parent.parent if layer.parent else None
		step = 0
		if font is not None:
			try:
				step = font.gridLength
			except AttributeError:
				grid = font.grid or 0
				step = grid / max(font.gridSubDivisions or 1, 1)
		if not step or step <= 0:
			return lambda v: v
		return lambda v: round(v / step) * step

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
