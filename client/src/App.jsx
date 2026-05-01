import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'

const API_BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1').replace(/\/$/, '')

const endpoints = {
  login: '/auth/login',
  rooms: '/rooms',
  roomRecommendations: '/rooms/recommend',
  roomsUpload: '/rooms/rooms/upload',
  studentsUpload: '/students/students/upload',
  subjectsFacultyUpload: '/subjects-faculty/upload',
  generateTimetable: '/timetable/generate',
  allTimetables: '/timetable/all',
  classTimetable: (name) => `/timetable/${encodeURIComponent(name)}`,
  bookings: '/bookings',
  bookingCalendar: '/bookings/calendar',
  bookingStatus: (id) => `/bookings/${id}/status`,
  bookingRoom: (id) => `/bookings/${id}/room`,
  bookingAppeal: (id) => `/bookings/${id}/appeal`,
}

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const SLOTS = ['1', '2', '3', '4', '5', '6']

const roleLabels = {
  administrator: 'Administrator',
  faculty: 'Faculty',
  club: 'Club',
}

const demoLogins = {
  administrator: { email: 'admin@campnou.edu', password: 'admin123' },
  faculty: { email: 'faculty@campnou.edu', password: 'faculty123' },
  club: { email: 'codingclub@campnou.edu', password: 'club123' },
}

const statusMeta = {
  idle: { label: 'Idle', tone: 'muted' },
  picking: { label: 'Ready', tone: 'info' },
  uploading: { label: 'Uploading', tone: 'info' },
  loading: { label: 'Loading', tone: 'info' },
  success: { label: 'Success', tone: 'success' },
  error: { label: 'Error', tone: 'error' },
}

const buildUrl = (path) => `${API_BASE}${path.startsWith('/') ? '' : '/'}${path}`

const parseError = async (response) => {
  try {
    const data = await response.json()
    return data?.detail || data?.message || 'Request failed'
  } catch {
    return 'Request failed'
  }
}

async function request(path, options = {}) {
  const headers = options.body instanceof FormData ? options.headers : {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  const response = await fetch(buildUrl(path), { ...options, headers })
  if (!response.ok) {
    const message = await parseError(response)
    throw new Error(message)
  }
  if (response.status === 204) return null
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return response.json()
  }
  return response.text()
}

function StatusPill({ status, label }) {
  const meta = statusMeta[status] || statusMeta.idle
  return <span className={`status-pill ${meta.tone}`}>{label || meta.label}</span>
}

function LoginPage({ onLogin }) {
  const [role, setRole] = useState('administrator')
  const [credentials, setCredentials] = useState(demoLogins.administrator)
  const [status, setStatus] = useState({ status: 'idle', message: 'Choose a role to continue.' })

  const switchRole = (nextRole) => {
    setRole(nextRole)
    setCredentials(demoLogins[nextRole])
    setStatus({ status: 'idle', message: `${roleLabels[nextRole]} login selected.` })
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setStatus({ status: 'loading', message: 'Signing in...' })

    try {
      const data = await request(endpoints.login, {
        method: 'POST',
        body: JSON.stringify({ ...credentials, role }),
      })
      setStatus({ status: 'success', message: 'Login successful.' })
      onLogin(data.user)
    } catch (error) {
      setStatus({ status: 'error', message: error.message })
    }
  }

  return (
    <div className="login-shell">
      <section className="login-panel">
        <div className="login-copy">
          <p className="eyebrow">Camp-nou</p>
          <h1>College scheduling and room booking portal</h1>
          <p>
            Sign in as admin, faculty, or club to reach the dashboard that matches your permissions.
          </p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="role-tabs" aria-label="Login role">
            {Object.entries(roleLabels).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={role === value ? 'active' : ''}
                onClick={() => switchRole(value)}
              >
                {label}
              </button>
            ))}
          </div>

          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={credentials.email}
              onChange={(event) => setCredentials((prev) => ({ ...prev, email: event.target.value }))}
              required
            />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={credentials.password}
              onChange={(event) => setCredentials((prev) => ({ ...prev, password: event.target.value }))}
              required
            />
          </label>

          <button type="submit" className="btn primary">Login</button>
          <div className="inline-status">
            <StatusPill status={status.status} />
            <span className="status-text">{status.message}</span>
          </div>
        </form>
      </section>
    </div>
  )
}

function TimetableGrid({ timetable }) {
  if (!timetable) return null

  return (
    <div className="timetable-grid">
      <div className="grid-row grid-header">
        <div className="grid-head" />
        {SLOTS.map((slot) => (
          <div key={`slot-${slot}`} className="grid-head">Slot {slot}</div>
        ))}
      </div>
      {DAYS.map((day) => (
        <div className="grid-row" key={day}>
          <div className="grid-day">{day}</div>
          {SLOTS.map((slot) => (
            <div className="grid-cell" key={`${day}-${slot}`}>
              <TimetableCell entry={timetable?.[day]?.[slot]} />
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function TimetableCell({ entry }) {
  if (!entry) return <span className="cell-empty">Empty</span>

  return (
    <div className={`cell-card ${entry.is_lab_period ? 'lab' : ''} ${entry.status !== 'scheduled' ? 'alert' : ''}`}>
      <strong>Subject {entry.subject_id ?? '-'}</strong>
      <span>Faculty {entry.faculty_id ?? '-'}</span>
      <span>Room {entry.room_id ?? '-'}</span>
      <div className="cell-tags">
        <span className="tag">{entry.is_lab_period ? 'Lab' : 'Class'}</span>
        <span className="tag ghost">{entry.status || 'scheduled'}</span>
      </div>
    </div>
  )
}

function CalendarView({ events }) {
  const groupedEvents = useMemo(() => {
    return events.reduce((acc, event) => {
      acc[event.event_date] = [...(acc[event.event_date] || []), event]
      return acc
    }, {})
  }, [events])

  if (!events.length) {
    return <p className="muted">No approved room bookings yet.</p>
  }

  return (
    <div className="calendar-list">
      {Object.entries(groupedEvents).map(([date, dayEvents]) => (
        <section className="calendar-day" key={date}>
          <time>{date}</time>
          <div className="calendar-events">
            {dayEvents.map((event) => (
              <article className="event-row" key={event.id}>
                <strong>{event.event_name}</strong>
                <span>{event.start_time} - {event.end_time}</span>
                <span>{event.club_name}</span>
                <span>{event.room_name}</span>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

const bookingTone = (status) => {
  if (status === 'approved') return 'success'
  if (status === 'rejected' || status === 'overridden') return 'error'
  if (status === 'appealed') return 'info'
  return 'idle'
}

function BookingList({ bookings, rooms = [], mode = 'admin', onUpdateStatus, onChangeRoom, onAppeal }) {
  const [roomEdits, setRoomEdits] = useState({})

  if (!bookings.length) {
    return <p className="muted">No booking notifications yet.</p>
  }

  return (
    <div className="booking-list">
      {bookings.map((booking) => (
        <article className="booking-row" key={booking.id}>
          <div>
            <strong>{booking.event_name}</strong>
            <span>{booking.club_name} requested {booking.room_name}</span>
            <span>{booking.event_date}, {booking.start_time} - {booking.end_time}</span>
            {booking.admin_note && <span className="notice-line">{booking.admin_note}</span>}
            {booking.conflicts?.length > 0 && (
              <div className="conflict-box">
                <strong>Clash evaluation</strong>
                {booking.conflicts.map((conflict) => (
                  <span key={conflict.id}>{conflict.status}: {conflict.event_name} by {conflict.club_name}</span>
                ))}
              </div>
            )}
          </div>
          <div className="booking-actions">
            <StatusPill status={bookingTone(booking.status)} label={booking.status} />
            {mode === 'admin' && booking.status === 'pending' && (
              <>
                <button type="button" className="btn primary compact" onClick={() => onUpdateStatus(booking.id, 'approved')}>Accept</button>
                <button type="button" className="btn ghost compact" onClick={() => onUpdateStatus(booking.id, 'rejected')}>Reject</button>
              </>
            )}
            {mode === 'admin' && booking.status === 'appealed' && (
              <button type="button" className="btn ghost compact" onClick={() => onUpdateStatus(booking.id, 'rejected')}>Close Appeal</button>
            )}
            {mode === 'admin' && ['approved', 'pending', 'overridden', 'appealed'].includes(booking.status) && rooms.length > 0 && (
              <div className="room-change">
                <select
                  value={roomEdits[booking.id] || booking.room_id || ''}
                  onChange={(event) => setRoomEdits((prev) => ({ ...prev, [booking.id]: event.target.value }))}
                >
                  <option value="">Change room</option>
                  {rooms.map((room) => (
                    <option value={room.id} key={room.id}>{room.name}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="btn ghost compact"
                  onClick={() => onChangeRoom(booking.id, roomEdits[booking.id] || booking.room_id)}
                >
                  Update Room
                </button>
              </div>
            )}
            {mode !== 'admin' && booking.status === 'overridden' && (
              <button type="button" className="btn primary compact" onClick={() => onAppeal(booking.id)}>Raise Appeal</button>
            )}
          </div>
        </article>
      ))}
    </div>
  )
}

function App() {
  const [user, setUser] = useState(null)
  const [apiStatus, setApiStatus] = useState({ status: 'idle', message: 'Not checked yet' })
  const [files, setFiles] = useState({ rooms: null, students: null, subjects: null })
  const [uploads, setUploads] = useState({
    rooms: { status: 'idle', message: 'No file selected' },
    students: { status: 'idle', message: 'No file selected' },
    subjects: { status: 'idle', message: 'No file selected' },
  })
  const [generation, setGeneration] = useState({
    status: 'idle',
    message: 'Timetable not generated yet.',
    warnings: [],
    classes: [],
  })
  const [allClasses, setAllClasses] = useState([])
  const [allStatus, setAllStatus] = useState({ status: 'idle', message: '' })
  const [selectedClass, setSelectedClass] = useState('')
  const [manualClass, setManualClass] = useState('')
  const [classView, setClassView] = useState({
    status: 'idle',
    message: 'Pick a class to preview the timetable.',
    className: '',
    timetable: null,
  })
  const [rooms, setRooms] = useState([])
  const [roomForm, setRoomForm] = useState({ name: '', capacity: '', room_type: 'classroom' })
  const [roomCreateStatus, setRoomCreateStatus] = useState({ status: 'idle', message: 'Add rooms manually or upload Excel.' })
  const [bookings, setBookings] = useState([])
  const [calendarEvents, setCalendarEvents] = useState([])
  const [bookingStatus, setBookingStatus] = useState({ status: 'idle', message: 'Ready for room requests.' })
  const [recommendationStatus, setRecommendationStatus] = useState({ status: 'idle', message: 'AI can suggest rooms after you enter event details.' })
  const [recommendations, setRecommendations] = useState([])
  const [bookingForm, setBookingForm] = useState({
    event_name: '',
    expected_attendees: '',
    equipment_needs: '',
    room_id: '',
    room_name: '',
    event_date: '',
    start_time: '',
    end_time: '',
  })

  const pendingBookings = bookings.filter((booking) => booking.status === 'pending' || booking.status === 'appealed')
  const isAdmin = user?.role === 'administrator'
  const isFaculty = user?.role === 'faculty'
  const isClub = user?.role === 'club'

  const updateUpload = (key, patch) => {
    setUploads((prev) => ({
      ...prev,
      [key]: { ...prev[key], ...patch },
    }))
  }

  const checkApi = useCallback(async () => {
    setApiStatus({ status: 'loading', message: 'Checking connectivity...' })
    try {
      await request(endpoints.allTimetables)
      setApiStatus({ status: 'success', message: 'Backend reachable.' })
    } catch (error) {
      setApiStatus({ status: 'error', message: error.message })
    }
  }, [])

  const refreshClasses = useCallback(async () => {
    setAllStatus({ status: 'loading', message: 'Loading classes...' })
    try {
      const data = await request(endpoints.allTimetables)
      const classes = Object.keys(data || {}).sort()
      setAllClasses(classes)
      setSelectedClass((prev) => (classes.includes(prev) ? prev : ''))
      setAllStatus({ status: 'success', message: classes.length ? 'Classes loaded.' : 'No timetables yet.' })
    } catch (error) {
      setAllStatus({ status: 'error', message: error.message })
    }
  }, [])

  const refreshRooms = useCallback(async () => {
    try {
      const data = await request(endpoints.rooms)
      setRooms(data?.rooms || [])
    } catch {
      setRooms([])
    }
  }, [])

  const refreshBookings = useCallback(async () => {
    if (!user) return
    try {
      const path = user.role === 'administrator'
        ? endpoints.bookings
        : `${endpoints.bookings}?requested_by_user_id=${user.id}`
      const data = await request(path)
      setBookings(data?.bookings || [])
    } catch {
      setBookings([])
    }
  }, [user])

  const refreshCalendar = useCallback(async () => {
    try {
      const data = await request(endpoints.bookingCalendar)
      setCalendarEvents(data?.events || [])
    } catch {
      setCalendarEvents([])
    }
  }, [])

  useEffect(() => {
    if (!user) return

    const timer = window.setTimeout(() => {
      checkApi()
      refreshClasses()
      refreshRooms()
      refreshCalendar()
      refreshBookings()
    }, 0)

    return () => window.clearTimeout(timer)
  }, [checkApi, refreshBookings, refreshCalendar, refreshClasses, refreshRooms, user])

  const handleFile = (key) => (event) => {
    const file = event.target.files?.[0] || null
    setFiles((prev) => ({ ...prev, [key]: file }))
    updateUpload(key, {
      status: file ? 'picking' : 'idle',
      message: file ? `Selected ${file.name}` : 'No file selected',
    })
  }

  const handleUpload = async (key, endpoint) => {
    const file = files[key]
    if (!file) {
      updateUpload(key, { status: 'error', message: 'Choose an Excel file first.' })
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    updateUpload(key, { status: 'uploading', message: 'Uploading...' })

    try {
      const data = await request(endpoint, { method: 'POST', body: formData })
      updateUpload(key, { status: 'success', message: data?.message || 'Upload complete.' })
      if (key === 'rooms') refreshRooms()
    } catch (error) {
      updateUpload(key, { status: 'error', message: error.message })
    }
  }

  const handleAddRoom = async (event) => {
    event.preventDefault()
    setRoomCreateStatus({ status: 'loading', message: 'Adding room...' })

    try {
      const data = await request(endpoints.rooms, {
        method: 'POST',
        body: JSON.stringify({
          name: roomForm.name,
          capacity: Number(roomForm.capacity),
          room_type: roomForm.room_type,
        }),
      })
      setRoomCreateStatus({ status: 'success', message: data?.message || 'Room added.' })
      setRoomForm({ name: '', capacity: '', room_type: 'classroom' })
      refreshRooms()
    } catch (error) {
      setRoomCreateStatus({ status: 'error', message: error.message })
    }
  }

  const handleGenerate = async () => {
    setGeneration({ status: 'loading', message: 'Generating timetable...', warnings: [], classes: [] })
    try {
      const data = await request(endpoints.generateTimetable, { method: 'POST' })
      setGeneration({
        status: 'success',
        message: data?.message || 'Generation completed.',
        warnings: data?.warnings || [],
        classes: data?.classes_scheduled || [],
      })
      refreshClasses()
    } catch (error) {
      setGeneration({ status: 'error', message: error.message, warnings: [], classes: [] })
    }
  }

  const loadClassTimetable = async (className) => {
    if (!className) {
      setClassView({ status: 'error', message: 'Enter or select a class name.', className: '', timetable: null })
      return
    }
    setClassView({ status: 'loading', message: 'Loading timetable...', className, timetable: null })
    try {
      const data = await request(endpoints.classTimetable(className))
      setClassView({
        status: 'success',
        message: 'Timetable loaded.',
        className: data?.class_name || className,
        timetable: data?.timetable || null,
      })
    } catch (error) {
      setClassView({ status: 'error', message: error.message, className, timetable: null })
    }
  }

  const downloadTimetablePdf = () => {
    if (!classView.timetable) return

    const rows = DAYS.map((day) => {
      const cells = SLOTS.map((slot) => {
        const entry = classView.timetable?.[day]?.[slot]
        const content = entry
          ? `Subject ${entry.subject_id ?? '-'}<br/>Faculty ${entry.faculty_id ?? '-'}<br/>Room ${entry.room_id ?? '-'}`
          : 'Empty'
        return `<td>${content}</td>`
      }).join('')
      return `<tr><th>${day}</th>${cells}</tr>`
    }).join('')

    const printWindow = window.open('', '_blank')
    printWindow.document.write(`
      <html>
        <head>
          <title>${classView.className} timetable</title>
          <style>
            body { font-family: Arial, sans-serif; color: #111; padding: 24px; }
            h1 { font-size: 24px; margin-bottom: 16px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #999; padding: 10px; vertical-align: top; font-size: 12px; }
            th { background: #eef2f5; text-align: left; }
          </style>
        </head>
        <body>
          <h1>${classView.className} Timetable</h1>
          <table>
            <thead><tr><th>Day</th>${SLOTS.map((slot) => `<th>Slot ${slot}</th>`).join('')}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </body>
      </html>
    `)
    printWindow.document.close()
    printWindow.focus()
    printWindow.print()
  }

  const submitBooking = async (event) => {
    event.preventDefault()
    setBookingStatus({ status: 'loading', message: 'Sending request to admin...' })

    const payload = {
      ...bookingForm,
      room_id: bookingForm.room_id ? Number(bookingForm.room_id) : null,
      club_name: isFaculty ? user.name : user.club_name || user.name,
      requested_by_user_id: user.id,
      requester_role: user.role,
    }

    try {
      const data = await request(endpoints.bookings, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setBookingStatus({ status: 'success', message: data?.message || 'Request sent.' })
      setBookingForm({
        event_name: '',
        expected_attendees: '',
        equipment_needs: '',
        room_id: '',
        room_name: '',
        event_date: '',
        start_time: '',
        end_time: '',
      })
      setRecommendations([])
      refreshBookings()
    } catch (error) {
      setBookingStatus({ status: 'error', message: error.message })
    }
  }

  const getRoomRecommendations = async () => {
    if (!bookingForm.event_name || !bookingForm.expected_attendees || !bookingForm.event_date || !bookingForm.start_time || !bookingForm.end_time) {
      setRecommendationStatus({ status: 'error', message: 'Enter event name, attendees, date, and time first.' })
      return
    }

    setRecommendationStatus({ status: 'loading', message: 'Finding the best rooms...' })
    try {
      const data = await request(endpoints.roomRecommendations, {
        method: 'POST',
        body: JSON.stringify({
          event_name: bookingForm.event_name,
          expected_attendees: Number(bookingForm.expected_attendees),
          event_date: bookingForm.event_date,
          start_time: bookingForm.start_time,
          end_time: bookingForm.end_time,
          equipment_needs: bookingForm.equipment_needs,
        }),
      })
      setRecommendations(data?.recommendations || [])
      setRecommendationStatus({
        status: 'success',
        message: data?.ai_used ? 'Gemini ranked the available rooms.' : 'Fallback ranking used because Gemini was unavailable.',
      })
    } catch (error) {
      setRecommendationStatus({ status: 'error', message: error.message })
    }
  }

  const chooseRecommendedRoom = (roomId) => {
    setBookingForm((prev) => ({ ...prev, room_id: String(roomId), room_name: '' }))
    setBookingStatus({ status: 'picking', message: 'Recommended room selected. Submit to request admin approval.' })
  }

  const updateBookingStatus = async (bookingId, status) => {
    try {
      await request(endpoints.bookingStatus(bookingId), {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      })
      refreshBookings()
      refreshCalendar()
    } catch (error) {
      setApiStatus({ status: 'error', message: error.message })
    }
  }

  const updateBookingRoom = async (bookingId, roomId) => {
    if (!roomId) {
      setApiStatus({ status: 'error', message: 'Choose a room before updating.' })
      return
    }

    try {
      await request(endpoints.bookingRoom(bookingId), {
        method: 'PATCH',
        body: JSON.stringify({ room_id: Number(roomId) }),
      })
      setApiStatus({ status: 'success', message: 'Booking room updated.' })
      refreshBookings()
      refreshCalendar()
    } catch (error) {
      setApiStatus({ status: 'error', message: error.message })
    }
  }

  const appealBooking = async (bookingId) => {
    try {
      const data = await request(endpoints.bookingAppeal(bookingId), { method: 'PATCH' })
      setBookingStatus({ status: 'success', message: data?.message || 'Appeal sent to admin.' })
      refreshBookings()
    } catch (error) {
      setBookingStatus({ status: 'error', message: error.message })
    }
  }

  if (!user) {
    return <LoginPage onLogin={setUser} />
  }

  return (
    <div className="page">
      <div className="backdrop" />
      <header className="topbar">
        <div className="brand">
          <span className="brand-title">Camp-nou</span>
          <span className="brand-sub">{roleLabels[user.role]} Dashboard</span>
        </div>
        <div className="top-actions">
          {isAdmin && <span className="notification-pill">{pendingBookings.length} pending bookings</span>}
          <div className="api-pill">
            <span>Signed in</span>
            <strong>{user.name}</strong>
          </div>
          <button type="button" className="btn ghost" onClick={checkApi}>Check API</button>
          <button type="button" className="btn ghost" onClick={() => setUser(null)}>Logout</button>
          <StatusPill status={apiStatus.status} />
        </div>
      </header>

      <main className="layout">
        {isAdmin && (
          <>
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Data Intake</h2>
                  <p>Upload Excel sheets that power the scheduler.</p>
                </div>
                <button type="button" className="btn ghost" onClick={refreshClasses}>Refresh Classes</button>
              </div>
              <div className="upload-grid">
                <UploadCard title="Rooms" description="Upload rooms inventory." status={uploads.rooms} onFile={handleFile('rooms')} onUpload={() => handleUpload('rooms', endpoints.roomsUpload)} />
                <UploadCard title="Students" description="Upload student roster sheets." status={uploads.students} onFile={handleFile('students')} onUpload={() => handleUpload('students', endpoints.studentsUpload)} />
                <UploadCard title="Subjects + Faculty" description="Upload subject-faculty mappings." status={uploads.subjects} onFile={handleFile('subjects')} onUpload={() => handleUpload('subjects', endpoints.subjectsFacultyUpload)} />
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Room Inventory</h2>
                  <p>Add rooms manually for booking recommendations and timetable scheduling.</p>
                </div>
                <div className="inline-status">
                  <StatusPill status={roomCreateStatus.status} />
                  <span className="status-text">{roomCreateStatus.message}</span>
                </div>
              </div>
              <form className="room-admin-form" onSubmit={handleAddRoom}>
                <label className="field">
                  <span>Room name</span>
                  <input value={roomForm.name} onChange={(event) => setRoomForm((prev) => ({ ...prev, name: event.target.value }))} required />
                </label>
                <label className="field">
                  <span>Capacity</span>
                  <input type="number" min="1" value={roomForm.capacity} onChange={(event) => setRoomForm((prev) => ({ ...prev, capacity: event.target.value }))} required />
                </label>
                <label className="field">
                  <span>Room type</span>
                  <select value={roomForm.room_type} onChange={(event) => setRoomForm((prev) => ({ ...prev, room_type: event.target.value }))}>
                    <option value="classroom">Classroom</option>
                    <option value="lab">Lab</option>
                    <option value="seminar">Seminar</option>
                    <option value="auditorium">Auditorium</option>
                  </select>
                </label>
                <button type="submit" className="btn primary">Add Room</button>
              </form>
              <div className="room-chip-row">
                {rooms.map((room) => (
                  <span className="room-chip" key={room.id}>{room.name} · {room.capacity} · {room.room_type}</span>
                ))}
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Scheduler</h2>
                  <p>Only administrators can generate timetables.</p>
                </div>
                <StatusPill status={generation.status} />
              </div>
              <div className="scheduler-body">
                <div className="scheduler-actions">
                  <button type="button" className="btn primary" onClick={handleGenerate}>Generate Timetable</button>
                  <p className="status-text">{generation.message}</p>
                </div>
                <div className="scheduler-output">
                  <div>
                    <h4>Warnings</h4>
                    {generation.warnings.length ? (
                      <ul>{generation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
                    ) : (
                      <p className="muted">No warnings reported yet.</p>
                    )}
                  </div>
                  <div>
                    <h4>Classes scheduled</h4>
                    {generation.classes.length ? (
                      <div className="tag-row">{generation.classes.map((name) => <span key={name} className="tag">{name}</span>)}</div>
                    ) : (
                      <p className="muted">Run generation to see classes.</p>
                    )}
                  </div>
                </div>
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Booking Notifications</h2>
                  <p>Evaluate clashes, approve faculty priority requests, and change rooms when needed.</p>
                </div>
                <button type="button" className="btn ghost" onClick={refreshBookings}>Refresh</button>
              </div>
              <BookingList
                bookings={bookings}
                rooms={rooms}
                mode="admin"
                onUpdateStatus={updateBookingStatus}
                onChangeRoom={updateBookingRoom}
              />
            </section>
          </>
        )}

        {(isAdmin || isFaculty) && (
          <section className="panel full">
            <div className="panel-header">
              <div>
                <h2>Timetable Explorer</h2>
                <p>{isFaculty ? 'Faculty can view and download generated timetables.' : 'Inspect generated class schedules.'}</p>
              </div>
              <div className="inline-status">
                <StatusPill status={allStatus.status} />
                <span className="status-text">{allStatus.message}</span>
              </div>
            </div>

            <TimetableControls
              classes={allClasses}
              selectedClass={selectedClass}
              setSelectedClass={setSelectedClass}
              manualClass={manualClass}
              setManualClass={setManualClass}
              onLoad={() => loadClassTimetable(manualClass || selectedClass)}
              onRefresh={refreshClasses}
              status={classView.status}
            />
            <p className="status-text">{classView.message}</p>
            {classView.timetable && (
              <div className="table-toolbar">
                <h3>{classView.className}</h3>
                <button type="button" className="btn primary" onClick={downloadTimetablePdf}>Download PDF</button>
              </div>
            )}
            <TimetableGrid timetable={classView.timetable} />
          </section>
        )}

        {(isClub || isFaculty) && (
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>{isFaculty ? 'Faculty Room Booking' : 'AI Room Booking'}</h2>
                <p>{isFaculty ? 'Faculty requests are evaluated by admin with higher priority.' : 'Enter event details for a recommendation, or choose a room manually.'}</p>
              </div>
              <div className="inline-status">
                <StatusPill status={bookingStatus.status} />
                <span className="status-text">{bookingStatus.message}</span>
              </div>
            </div>

            <form className="booking-form" onSubmit={submitBooking}>
              <label className="field">
                <span>Event name</span>
                <input value={bookingForm.event_name} onChange={(event) => setBookingForm((prev) => ({ ...prev, event_name: event.target.value }))} required />
              </label>
              <label className="field">
                <span>Expected attendees</span>
                <input type="number" min="1" value={bookingForm.expected_attendees} onChange={(event) => setBookingForm((prev) => ({ ...prev, expected_attendees: event.target.value }))} required />
              </label>
              <label className="field wide">
                <span>Equipment needs</span>
                <input value={bookingForm.equipment_needs} onChange={(event) => setBookingForm((prev) => ({ ...prev, equipment_needs: event.target.value }))} placeholder="Projector, speakers, lab systems..." />
              </label>
              <label className="field">
                <span>Room</span>
                {rooms.length ? (
                  <select value={bookingForm.room_id} onChange={(event) => setBookingForm((prev) => ({ ...prev, room_id: event.target.value }))} required>
                    <option value="">Choose room</option>
                    {rooms.map((room) => (
                      <option value={room.id} key={room.id}>{room.name} ({room.capacity})</option>
                    ))}
                  </select>
                ) : (
                  <input value={bookingForm.room_name} onChange={(event) => setBookingForm((prev) => ({ ...prev, room_name: event.target.value }))} placeholder="Room name" required />
                )}
              </label>
              <label className="field">
                <span>Date</span>
                <input type="date" value={bookingForm.event_date} onChange={(event) => setBookingForm((prev) => ({ ...prev, event_date: event.target.value }))} required />
              </label>
              <label className="field">
                <span>Start time</span>
                <input type="time" value={bookingForm.start_time} onChange={(event) => setBookingForm((prev) => ({ ...prev, start_time: event.target.value }))} required />
              </label>
              <label className="field">
                <span>End time</span>
                <input type="time" value={bookingForm.end_time} onChange={(event) => setBookingForm((prev) => ({ ...prev, end_time: event.target.value }))} required />
              </label>
              <button type="button" className="btn ghost" onClick={getRoomRecommendations}>Recommend Rooms</button>
              <button type="submit" className="btn primary">Request Booking</button>
            </form>

            <div className="recommendation-status">
              <StatusPill status={recommendationStatus.status} />
              <span className="status-text">{recommendationStatus.message}</span>
            </div>

            {recommendations.length > 0 && (
              <div className="recommendation-grid">
                {recommendations.map((room) => (
                  <article className={`recommendation-card ${String(room.id) === bookingForm.room_id ? 'selected' : ''}`} key={room.id}>
                    <div>
                      <strong>{room.name}</strong>
                      <span>{room.room_type} · {room.capacity} seats · score {room.score}</span>
                    </div>
                    <p>{room.reason}</p>
                    {room.pending_conflicts > 0 && (
                      <span className="pending-note">{room.pending_conflicts} pending request at this time</span>
                    )}
                    <button type="button" className="btn primary compact" onClick={() => chooseRecommendedRoom(room.id)}>Use This Room</button>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}

        {(isClub || isFaculty) && (
          <section className="panel full">
            <div className="panel-header">
              <div>
                <h2>My Booking Updates</h2>
                <p>Track approvals, overrides, and appeals for your room requests.</p>
              </div>
              <button type="button" className="btn ghost" onClick={refreshBookings}>Refresh Updates</button>
            </div>
            <BookingList bookings={bookings} mode="user" onAppeal={appealBooking} />
          </section>
        )}

        {(isAdmin || isClub) && (
          <section className="panel full">
            <div className="panel-header">
              <div>
                <h2>Club Calendar</h2>
                <p>Approved room bookings are visible to clubs.</p>
              </div>
              <button type="button" className="btn ghost" onClick={refreshCalendar}>Refresh Calendar</button>
            </div>
            <CalendarView events={calendarEvents} />
          </section>
        )}
      </main>
    </div>
  )
}

function UploadCard({ title, description, status, onFile, onUpload }) {
  return (
    <div className="file-card">
      <header>
        <h3>{title}</h3>
        <StatusPill status={status.status} />
      </header>
      <p>{description}</p>
      <input type="file" accept=".xlsx,.xls" onChange={onFile} />
      <div className="file-meta">{status.message}</div>
      <button type="button" className="btn primary" onClick={onUpload}>Upload</button>
    </div>
  )
}

function TimetableControls({
  classes,
  selectedClass,
  setSelectedClass,
  manualClass,
  setManualClass,
  onLoad,
  onRefresh,
  status,
}) {
  return (
    <div className="explorer-controls">
      <label className="field">
        <span>Pick a class</span>
        <select value={selectedClass} onChange={(event) => setSelectedClass(event.target.value)}>
          <option value="">Select class</option>
          {classes.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
      </label>
      <label className="field">
        <span>Or enter manually</span>
        <input type="text" placeholder="e.g. CS-A" value={manualClass} onChange={(event) => setManualClass(event.target.value)} />
      </label>
      <button type="button" className="btn primary" onClick={onLoad}>Load Timetable</button>
      <button type="button" className="btn ghost" onClick={onRefresh}>Refresh</button>
      <StatusPill status={status} />
    </div>
  )
}

export default App
