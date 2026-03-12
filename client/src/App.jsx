import { useCallback, useEffect, useState } from 'react'
import './App.css'

const API_BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1').replace(/\/$/, '')

const endpoints = {
  roomsUpload: '/rooms/rooms/upload',
  studentsUpload: '/students/students/upload',
  subjectsFacultyUpload: '/subjects-faculty/upload',
  generateTimetable: '/timetable/generate',
  allTimetables: '/timetable/all',
  classTimetable: (name) => `/timetable/${encodeURIComponent(name)}`,
}

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const SLOTS = ['1', '2', '3', '4', '5', '6']

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
  const response = await fetch(buildUrl(path), options)
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

function StatusPill({ status }) {
  const meta = statusMeta[status] || statusMeta.idle
  return <span className={`status-pill ${meta.tone}`}>{meta.label}</span>
}

function App() {
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

  const apiHint = API_BASE

  const updateUpload = (key, patch) => {
    setUploads((prev) => ({
      ...prev,
      [key]: { ...prev[key], ...patch },
    }))
  }

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
      const data = await request(endpoint, {
        method: 'POST',
        body: formData,
      })
      updateUpload(key, {
        status: 'success',
        message: data?.message || 'Upload complete.',
      })
    } catch (error) {
      updateUpload(key, { status: 'error', message: error.message })
    }
  }

  const refreshClasses = useCallback(async (seed) => {
    setAllStatus({ status: 'loading', message: 'Loading classes...' })
    try {
      const data = seed ?? (await request(endpoints.allTimetables))
      const classes = Object.keys(data || {}).sort()
      setAllClasses(classes)
      setSelectedClass((prev) => (classes.includes(prev) ? prev : ''))
      setAllStatus({ status: 'success', message: classes.length ? 'Classes loaded.' : 'No timetables yet.' })
    } catch (error) {
      setAllStatus({ status: 'error', message: error.message })
    }
  }, [])

  const checkApi = useCallback(async () => {
    setApiStatus({ status: 'loading', message: 'Checking connectivity...' })
    try {
      const data = await request(endpoints.allTimetables)
      setApiStatus({ status: 'success', message: 'Backend reachable.' })
      refreshClasses(data)
    } catch (error) {
      setApiStatus({ status: 'error', message: error.message })
    }
  }, [refreshClasses])

  useEffect(() => {
    checkApi()
  }, [checkApi])

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
      setClassView({
        status: 'error',
        message: 'Enter or select a class name.',
        className: '',
        timetable: null,
      })
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

  const renderCell = (entry) => {
    if (!entry) return <span className="cell-empty">—</span>
    return (
      <div className={`cell-card ${entry.is_lab_period ? 'lab' : ''} ${entry.status !== 'scheduled' ? 'alert' : ''}`}>
        <strong>Subject {entry.subject_id ?? '—'}</strong>
        <span>Faculty {entry.faculty_id ?? '—'}</span>
        <span>Room {entry.room_id ?? '—'}</span>
        <div className="cell-tags">
          <span className="tag">{entry.is_lab_period ? 'Lab' : 'Class'}</span>
          <span className="tag ghost">{entry.status || 'scheduled'}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="backdrop" />
      <header className="topbar">
        <div className="brand">
          <span className="brand-title">Camp-nou</span>
          <span className="brand-sub">Timetable Orchestration Console</span>
        </div>
        <div className="top-actions">
          <div className="api-pill">
            <span>API</span>
            <strong>{apiHint}</strong>
          </div>
          <button type="button" className="btn ghost" onClick={checkApi}>
            Check API
          </button>
          <StatusPill status={apiStatus.status} />
        </div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">Backend sync ready</p>
          <h1>Upload inputs, generate the timetable, and explore every class in one flow.</h1>
          <p className="lede">
            This frontend mirrors the FastAPI contract. Upload Excel sheets, trigger the scheduler, and review
            class-level grids without leaving the dashboard.
          </p>
        </div>
        <div className="hero-card">
          <h3>Live Sync Status</h3>
          <p>{apiStatus.message}</p>
          <div className="hero-meta">
            <div>
              <span>Rooms upload</span>
              <StatusPill status={uploads.rooms.status} />
            </div>
            <div>
              <span>Students upload</span>
              <StatusPill status={uploads.students.status} />
            </div>
            <div>
              <span>Subjects + Faculty</span>
              <StatusPill status={uploads.subjects.status} />
            </div>
          </div>
        </div>
      </section>

      <main className="layout">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Data Intake</h2>
              <p>Upload Excel sheets that power the scheduler.</p>
            </div>
            <button type="button" className="btn ghost" onClick={refreshClasses}>
              Refresh Classes
            </button>
          </div>
          <div className="upload-grid">
            <div className="file-card">
              <header>
                <h3>Rooms</h3>
                <StatusPill status={uploads.rooms.status} />
              </header>
              <p>Upload the rooms inventory (.xlsx / .xls).</p>
              <input type="file" accept=".xlsx,.xls" onChange={handleFile('rooms')} />
              <div className="file-meta">{uploads.rooms.message}</div>
              <button
                type="button"
                className="btn primary"
                onClick={() => handleUpload('rooms', endpoints.roomsUpload)}
              >
                Upload Rooms
              </button>
            </div>

            <div className="file-card">
              <header>
                <h3>Students</h3>
                <StatusPill status={uploads.students.status} />
              </header>
              <p>Upload student roster sheets for class mapping.</p>
              <input type="file" accept=".xlsx,.xls" onChange={handleFile('students')} />
              <div className="file-meta">{uploads.students.message}</div>
              <button
                type="button"
                className="btn primary"
                onClick={() => handleUpload('students', endpoints.studentsUpload)}
              >
                Upload Students
              </button>
            </div>

            <div className="file-card">
              <header>
                <h3>Subjects + Faculty</h3>
                <StatusPill status={uploads.subjects.status} />
              </header>
              <p>Upload subject-faculty mapping and class assignments.</p>
              <input type="file" accept=".xlsx,.xls" onChange={handleFile('subjects')} />
              <div className="file-meta">{uploads.subjects.message}</div>
              <button
                type="button"
                className="btn primary"
                onClick={() => handleUpload('subjects', endpoints.subjectsFacultyUpload)}
              >
                Upload Mapping
              </button>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Scheduler</h2>
              <p>Trigger the timetable generation and track warnings.</p>
            </div>
            <StatusPill status={generation.status} />
          </div>
          <div className="scheduler-body">
            <div className="scheduler-actions">
              <button type="button" className="btn primary" onClick={handleGenerate}>
                Generate Timetable
              </button>
              <p className="status-text">{generation.message}</p>
            </div>
            <div className="scheduler-output">
              <div>
                <h4>Warnings</h4>
                {generation.warnings.length ? (
                  <ul>
                    {generation.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No warnings reported yet.</p>
                )}
              </div>
              <div>
                <h4>Classes scheduled</h4>
                {generation.classes.length ? (
                  <div className="tag-row">
                    {generation.classes.map((name) => (
                      <span key={name} className="tag">
                        {name}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="muted">Run generation to see classes.</p>
                )}
              </div>
            </div>
          </div>
        </section>

        <section className="panel full">
          <div className="panel-header">
            <div>
              <h2>Timetable Explorer</h2>
              <p>Inspect a class schedule as a 6-slot grid.</p>
            </div>
            <div className="inline-status">
              <StatusPill status={allStatus.status} />
              <span className="status-text">{allStatus.message}</span>
            </div>
          </div>

          <div className="explorer-controls">
            <label className="field">
              <span>Pick a class</span>
              <select value={selectedClass} onChange={(event) => setSelectedClass(event.target.value)}>
                <option value="">Select class</option>
                {allClasses.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Or enter manually</span>
              <input
                type="text"
                placeholder="e.g. CS-A"
                value={manualClass}
                onChange={(event) => setManualClass(event.target.value)}
              />
            </label>
            <button
              type="button"
              className="btn primary"
              onClick={() => loadClassTimetable(manualClass || selectedClass)}
            >
              Load Timetable
            </button>
            <StatusPill status={classView.status} />
          </div>

          <p className="status-text">{classView.message}</p>

          {classView.timetable && (
            <div className="timetable-grid">
              <div className="grid-row grid-header">
                <div className="grid-head" />
                {SLOTS.map((slot) => (
                  <div key={`slot-${slot}`} className="grid-head">
                    Slot {slot}
                  </div>
                ))}
              </div>
              {DAYS.map((day) => (
                <div className="grid-row" key={day}>
                  <div className="grid-day">{day}</div>
                  {SLOTS.map((slot) => (
                    <div className="grid-cell" key={`${day}-${slot}`}>
                      {renderCell(classView.timetable?.[day]?.[slot])}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

export default App
