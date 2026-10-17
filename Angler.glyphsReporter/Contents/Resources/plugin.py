# encoding: utf-8

###########################################################################################################
#
#	Angler — Reporter Plugin
#
#	Shows the angle (0–180° from horizontal) of selected line segments,
#	BCP handles, and the handles of selected nodes in the Edit View.
#
###########################################################################################################

from __future__ import division, print_function, unicode_literals
import objc
from math import atan2, degrees, hypot
from GlyphsApp import Glyphs, OFFCURVE, LINE
from GlyphsApp.plugins import ReporterPlugin
from AppKit import (
	NSAttributedString,
	NSBezierPath,
	NSColor,
	NSFont,
	NSFontAttributeName,
	NSForegroundColorAttributeName,
	NSMakePoint,
	NSMakeRect,
)

# All sizes are in screen points and get divided by the zoom scale.
FONT_SIZE = 10.0
BADGE_PAD_X = 4.0
BADGE_PAD_Y = 2.0
BADGE_GAP = 4.0
ARC_RADIUS = 16.0
TICK_LENGTH = 22.0
LINE_WIDTH = 1.0

# Angles within this many degrees of an axis (but not on it) get flagged.
NEAR_AXIS_TOLERANCE = 0.5
ON_AXIS_EPSILON = 1e-6


def rgba(r, g, b, a):
	return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)


COLOR_NORMAL = rgba(0.15, 0.15, 0.15, 0.85)
COLOR_NEAR_AXIS = rgba(1.0, 0.5, 0.0, 0.95)
COLOR_ON_AXIS = rgba(0.15, 0.6, 0.3, 0.9)
COLOR_TEXT = rgba(1.0, 1.0, 1.0, 1.0)


def angle_of(a, b):
	"""Direction-agnostic angle of the line a→b, in [0, 180)."""
	return degrees(atan2(b[1] - a[1], b[0] - a[0])) % 180.0


def axis_deviation(angle):
	return min(angle, abs(angle - 90.0), 180.0 - angle)


class Angler(ReporterPlugin):

	@objc.python_method
	def settings(self):
		self.menuName = Glyphs.localize({
			'en': 'Angler',
		})

	@objc.python_method
	def foreground(self, layer):
		scale = self.getScale()
		if not scale:
			return
		for anchor, other in self.collect_pairs(layer):
			self.draw_measurement(anchor, other, scale)

	@objc.python_method
	def collect_pairs(self, layer):
		"""Returns a list of (anchor, other) point tuples to measure."""
		pairs = []
		seen = set()
		selected = []

		def add(path_index, i, j, nodes):
			key = frozenset(((path_index, i), (path_index, j)))
			if i == j or key in seen:
				return
			seen.add(key)
			a, b = nodes[i], nodes[j]
			pairs.append(((a.x, a.y), (b.x, b.y)))

		for path_index, path in enumerate(layer.paths):
			nodes = list(path.nodes)
			count = len(nodes)
			closed = path.closed

			def neighbor(i, step):
				j = i + step
				if 0 <= j < count:
					return j
				return j % count if closed and count > 1 else None

			for i, node in enumerate(nodes):
				if not node.selected:
					continue
				selected.append((path_index, i, node))
				prev_i = neighbor(i, -1)
				next_i = neighbor(i, 1)

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
			if key not in seen:
				pairs.append(((a.x, a.y), (b.x, b.y)))

		return [p for p in pairs if hypot(p[1][0] - p[0][0], p[1][1] - p[0][1]) > 0]

	@objc.python_method
	def draw_measurement(self, anchor, other, scale):
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
		self.draw_badge(anchor, other, dx, dy, length, angle, color, scale)

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

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
