// Round-robin meeting-room scheduler: assigns bookings to rooms without overlap.

'use strict';

function toMinutes(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(m) || h > 23 || m > 59) {
    throw new RangeError(`bad time: ${hhmm}`);
  }
  return h * 60 + m;
}

function overlaps(a, b) {
  return a.start < b.end && b.start < a.end;
}

class Room {
  constructor(name, capacity) {
    this.name = name;
    this.capacity = capacity;
    this.bookings = [];
  }

  canHost(request) {
    if (request.attendees > this.capacity) return false;
    return !this.bookings.some((b) => overlaps(b, request));
  }

  book(request) {
    this.bookings.push(request);
    this.bookings.sort((x, y) => x.start - y.start);
  }

  utilisation(dayStart, dayEnd) {
    const used = this.bookings.reduce((acc, b) => acc + (b.end - b.start), 0);
    return used / (dayEnd - dayStart);
  }
}

function schedule(rooms, requests) {
  const assigned = [];
  const rejected = [];
  let cursor = 0;
  const ordered = requests
    .map((r) => ({ ...r, start: toMinutes(r.from), end: toMinutes(r.to) }))
    .sort((a, b) => a.start - b.start || b.attendees - a.attendees);
  for (const req of ordered) {
    let placed = false;
    for (let tried = 0; tried < rooms.length; tried++) {
      const room = rooms[(cursor + tried) % rooms.length];
      if (room.canHost(req)) {
        room.book(req);
        assigned.push({ id: req.id, room: room.name });
        cursor = (cursor + tried + 1) % rooms.length;
        placed = true;
        break;
      }
    }
    if (!placed) {
      rejected.push(req.id);
    }
  }
  return { assigned, rejected };
}

function report(rooms) {
  const lines = [];
  for (const room of rooms) {
    const pct = Math.round(room.utilisation(toMinutes('08:00'), toMinutes('20:00')) * 100);
    lines.push(`${room.name.padEnd(10)} ${String(room.bookings.length).padStart(3)} bookings ${pct}%`);
  }
  return lines.join('\n');
}

if (require.main === module) {
  const rooms = [new Room('Hanok', 6), new Room('Baekdu', 12), new Room('Jeju', 4)];
  const result = schedule(rooms, [
    { id: 'r1', from: '09:00', to: '10:00', attendees: 5 },
    { id: 'r2', from: '09:30', to: '11:00', attendees: 10 },
    { id: 'r3', from: '09:45', to: '10:15', attendees: 3 },
    { id: 'r4', from: '09:50', to: '10:30', attendees: 4 },
    { id: 'r5', from: '13:00', to: '14:00', attendees: 20 },
  ]);
  console.log(result);
  console.log(report(rooms));
}

module.exports = { schedule, report, Room, toMinutes };
