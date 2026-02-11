import { useEffect, useMemo, useState } from 'react'
import './App.css'

const metrics = [
  {
    label: 'Conflict Reduction Target',
    value: '80%',
    note: 'Focused on minimizing scheduling clashes campus-wide.'
  },
  {
    label: 'Room Utilization Gain',
    value: '60%',
    note: 'Improved capacity usage through intelligent allocation.'
  },
  {
    label: 'Reschedule Response',
    value: 'Minutes',
    note: 'From hours to minutes for urgent changes.'
  }
]

const narrative = [
  {
    title: 'Problem',
    text: 'Manual scheduling causes conflicts, wasted rooms, and uneven access.'
  },
  {
    title: 'Insight',
    text: 'Agentic negotiation and policy-driven rules outperform rigid timetables.'
  },
  {
    title: 'Outcome',
    text: 'Faster decisions, fairer distribution, and measurable efficiency gains.'
  }
]

const scope = [
  'Automate classroom and facility allocation with intelligent conflict resolution.',
  'Adapt to policy changes like priority rules and exam occupancy limits.',
  'Distribute resources fairly across departments, clubs, and exam cells.',
  'Generate transparent audit logs with decision rationale.',
  'Scale across departments with role-based access and security.'
]

const workflow = [
  {
    title: 'Upload',
    text: 'Admins upload student and course data via Excel.'
  },
  {
    title: 'Allocate',
    text: 'Agentic AI assigns students to classes using capacity and policy rules.'
  },
  {
    title: 'Audit',
    text: 'Every decision is logged for accountability and review.'
  }
]

const agents = [
  'Department Agents for requests and preferences.',
  'Facility Management Agent for rooms and maintenance.',
  'Scheduling Optimization Agent for global conflict resolution.',
  'Policy Enforcement Agent for priorities and compliance.',
  'Exam Cell Agent for high-priority scheduling.',
  'Club Agents for event space allocation.'
]

const capabilities = [
  'Automated conflict detection and resolution.',
  'Dynamic prioritization: classes, admin units, then clubs.',
  'Emergency reallocation with real-time updates.',
  'Secure RBAC-based access for each stakeholder role.',
  'RAG-backed decisions grounded in institutional data.'
]

const futures = [
  'Multi-institution resource sharing.',
  'Predictive analytics for demand forecasting.',
  'Reinforcement learning for smarter negotiations.',
  'Real-time room availability monitoring.'
]

const roles = [
  {
    title: 'Admin',
    text: 'Uploads data, monitors allocations, and manages policies.'
  },
  {
    title: 'Teacher',
    text: 'Views assigned classrooms and flags conflicts.'
  },
  {
    title: 'Student',
    text: 'Receives class assignments and schedule updates.'
  }
]

const clubs = [
  'EXCEL',
  'IEDC',
  'MACS',
  'IEEE',
  'EMF',
  'FOSS',
  'Bharatham',
  'TEDx'
]

const venues = [
  'SDPK',
  'Internal Auditorium',
  'External Auditorium',
  'Media Hall',
  'Amphie Theater'
]

function App() {
  const [metricIndex, setMetricIndex] = useState(0)
  const [view, setView] = useState('landing')
  const [theme, setTheme] = useState('light')
  const [selectedClub, setSelectedClub] = useState('')
  const [selectedVenue, setSelectedVenue] = useState('')
  const [selectedDate, setSelectedDate] = useState('')
  const [notice, setNotice] = useState('')

  const metric = useMemo(() => metrics[metricIndex], [metricIndex])

  useEffect(() => {
    const stored = window.localStorage.getItem('campnou-theme')
    if (stored) {
      setTheme(stored)
    }
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    window.localStorage.setItem('campnou-theme', theme)
  }, [theme])

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 3200)
    return () => window.clearTimeout(timer)
  }, [notice])

  const handleCycle = () => {
    setMetricIndex((prev) => (prev + 1) % metrics.length)
  }

  const handleMove = (event) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    event.currentTarget.style.setProperty('--spot-x', `${x}px`)
    event.currentTarget.style.setProperty('--spot-y', `${y}px`)
  }

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))
  }

  const handleBooking = () => {
    if (!selectedClub || !selectedVenue || !selectedDate) return
    setNotice(`Booked ${selectedClub} at ${selectedVenue} on ${selectedDate}`)
  }

  if (view === 'login' || view === 'signup') {
    return (
      <div className="page" onMouseMove={handleMove}>
        <div className="orb orb-one" />
        <div className="orb orb-two" />
        <div className="orb orb-three" />
        <header className="topbar">
          <button type="button" className="brand" onClick={() => setView('landing')}>
            Camp-nou
          </button>
          <div className="nav-actions">
            <button type="button" className="btn ghost theme-toggle" onClick={toggleTheme}>
              {theme === 'light' ? 'Dark mode' : 'Light mode'}
            </button>
            <button type="button" className="btn ghost" onClick={() => setView('landing')}>
              Back to overview
            </button>
          </div>
        </header>

        <section className="auth-shell">
          <div className="auth-copy">
            <span className="eyebrow">Agentic AI Scheduling</span>
            <h1>{view === 'login' ? 'Welcome back' : 'Create your workspace'}</h1>
            <p className="lede">
              {view === 'login'
                ? 'Access the intelligent allocation dashboard based on your role.'
                : 'Set up your access profile to start scheduling instantly.'}
            </p>
            <div className="role-grid">
              {roles.map((role) => (
                <div key={role.title} className="role-card">
                  <h3>{role.title}</h3>
                  <p>{role.text}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="auth-card">
            <div className="auth-header">
              <span>{view === 'login' ? 'Login' : 'Sign Up'}</span>
              <span className="pill">No backend yet</span>
            </div>
            <form className="auth-form">
              <label>
                Email
                <input type="email" placeholder="name@institution.edu" />
              </label>
              <label>
                Password
                <input type="password" placeholder="••••••••" />
              </label>
              {view === 'signup' && (
                <label>
                  Confirm password
                  <input type="password" placeholder="••••••••" />
                </label>
              )}
              <div className="role-select">
                <span>Role</span>
                <div className="role-buttons">
                  <button type="button" className="pill">
                    Admin
                  </button>
                  <button type="button" className="pill">
                    Teacher
                  </button>
                  <button type="button" className="pill">
                    Student
                  </button>
                </div>
              </div>
              <button type="button" className="btn primary full" onClick={() => setView('booking')}>
                {view === 'login' ? 'Login' : 'Create account'}
              </button>
            </form>
            <div className="auth-footer">
              {view === 'login' ? (
                <p>
                  Need an account?{' '}
                  <button type="button" className="link" onClick={() => setView('signup')}>
                    Sign up
                  </button>
                </p>
              ) : (
                <p>
                  Already have access?{' '}
                  <button type="button" className="link" onClick={() => setView('login')}>
                    Login
                  </button>
                </p>
              )}
            </div>
          </div>
        </section>
      </div>
    )
  }

  if (view === 'booking') {
    return (
      <div className="page" onMouseMove={handleMove}>
        <div className="orb orb-one" />
        <div className="orb orb-two" />
        <div className="orb orb-three" />

        <header className="topbar">
          <button type="button" className="brand" onClick={() => setView('landing')}>
            Camp-nou
          </button>
          <div className="nav-actions">
            <button type="button" className="btn ghost theme-toggle" onClick={toggleTheme}>
              {theme === 'light' ? 'Dark mode' : 'Light mode'}
            </button>
            <button type="button" className="btn ghost" onClick={() => setView('landing')}>
              Back to overview
            </button>
          </div>
        </header>

        <section className="booking-shell">
          <div className="booking-copy">
            <span className="eyebrow">Club Booking</span>
            <h1>Reserve halls with confidence</h1>
            <p className="lede">
              Pick your club, select a venue, and lock in the date. The system will
              confirm instantly.
            </p>
            <div className="booking-grid">
              <div className="booking-card">
                <h3>Available Clubs</h3>
                <div className="chip-grid">
                  {clubs.map((club) => (
                    <button
                      key={club}
                      type="button"
                      className={`chip selectable ${selectedClub === club ? 'active' : ''}`}
                      onClick={() => setSelectedClub(club)}
                    >
                      {club}
                    </button>
                  ))}
                </div>
              </div>
              <div className="booking-card">
                <h3>Venues</h3>
                <div className="chip-grid">
                  {venues.map((venue) => (
                    <button
                      key={venue}
                      type="button"
                      className={`chip selectable ${selectedVenue === venue ? 'active' : ''}`}
                      onClick={() => setSelectedVenue(venue)}
                    >
                      {venue}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="booking-panel">
            <div className="booking-card highlight">
              <div className="booking-header">
                <span>Booking details</span>
                <span className="pill">No backend yet</span>
              </div>
              <div className="booking-form">
                <label className="field">
                  Club
                  <select value={selectedClub} onChange={(event) => setSelectedClub(event.target.value)}>
                    <option value="">Select club</option>
                    {clubs.map((club) => (
                      <option key={club} value={club}>
                        {club}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Venue
                  <select value={selectedVenue} onChange={(event) => setSelectedVenue(event.target.value)}>
                    <option value="">Select venue</option>
                    {venues.map((venue) => (
                      <option key={venue} value={venue}>
                        {venue}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Date
                  <input
                    type="date"
                    value={selectedDate}
                    onChange={(event) => setSelectedDate(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="btn primary full"
                  onClick={handleBooking}
                  disabled={!selectedClub || !selectedVenue || !selectedDate}
                >
                  Book now
                </button>
                <p className="booking-hint">
                  Bookings are confirmed instantly and logged for audit review.
                </p>
              </div>
            </div>
          </div>
        </section>

        {notice && <div className="toast">{notice}</div>}
      </div>
    )
  }

  return (
    <div className="page" onMouseMove={handleMove}>
      <div className="orb orb-one" />
      <div className="orb orb-two" />
      <div className="orb orb-three" />

      <header className="topbar">
        <button type="button" className="brand" onClick={() => setView('landing')}>
          Camp-nou
        </button>
        <div className="nav-actions">
          <button type="button" className="btn ghost theme-toggle" onClick={toggleTheme}>
            {theme === 'light' ? 'Dark mode' : 'Light mode'}
          </button>
          <button type="button" className="btn ghost" onClick={() => setView('login')}>
            Login
          </button>
          <button type="button" className="btn primary" onClick={() => setView('signup')}>
            Sign up
          </button>
        </div>
      </header>

      <header className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Agentic AI Scheduling</span>
          <h1>Camp-nou</h1>
          <p className="lede">
            Camp-Nou — Where Decisions Score Big. Agentic AI that assigns students to
            classrooms with fairness, speed, and auditable decision-making.
          </p>
          <div className="cta-row">
            <button type="button" className="btn primary" onClick={() => setView('signup')}>
              Explore the system
            </button>
            <button type="button" className="btn ghost" onClick={() => setView('login')}>
              View dashboard
            </button>
          </div>
          <div className="meta-grid">
            <div>
              <span className="meta-label">Core flow</span>
              <span className="meta-value">Excel upload → Agentic allocation</span>
            </div>
            <div>
              <span className="meta-label">Backend</span>
              <span className="meta-value">LangGraph + Python agents</span>
            </div>
            <div>
              <span className="meta-label">Security</span>
              <span className="meta-value">RBAC for every stakeholder</span>
            </div>
          </div>
        </div>

        <div className="hero-visual">
          <div className="metric-card">
            <div className="metric-header">
              <span>Key performance targets</span>
              <button type="button" className="pill" onClick={handleCycle}>
                Tap to cycle
              </button>
            </div>
            <div className="metric-value">{metric.value}</div>
            <div className="metric-label">{metric.label}</div>
            <p className="metric-note">{metric.note}</p>
          </div>

          <div className="signal-grid">
            <div className="signal-item">
              <span className="signal-tag">Agentic</span>
              <p>Decentralized decisions without a single point of failure.</p>
            </div>
            <div className="signal-item">
              <span className="signal-tag">Adaptive</span>
              <p>Policy changes and emergencies handled in minutes.</p>
            </div>
            <div className="signal-item">
              <span className="signal-tag">Auditable</span>
              <p>Every allocation has a logged rationale.</p>
            </div>
          </div>
        </div>
      </header>

      <section className="section">
        <div className="section-head">
          <h2>Core Narrative</h2>
          <p>Concise signals that explain why the system exists.</p>
        </div>
        <div className="cards">
          {narrative.map((item) => (
            <article key={item.title} className="card">
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>How It Works</h2>
          <p>Three steps that turn raw data into fair schedules.</p>
        </div>
        <div className="timeline">
          {workflow.map((step, index) => (
            <div key={step.title} className="step">
              <span className="step-index">0{index + 1}</span>
              <div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>System Capabilities</h2>
          <p>Built for fairness, speed, and continuous institutional alignment.</p>
        </div>
        <div className="chip-grid">
          {capabilities.map((item) => (
            <span key={item} className="chip">
              {item}
            </span>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Agent Roles</h2>
          <p>Specialized agents collaborate to resolve conflicts and optimize usage.</p>
        </div>
        <div className="cards">
          {agents.map((item) => (
            <article key={item} className="card compact">
              <p>{item}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Project Scope</h2>
          <p>Precisely scoped to avoid feature bloat and maximize impact.</p>
        </div>
        <div className="scope-list">
          {scope.map((item) => (
            <div key={item} className="scope-item">
              <span className="scope-dot" />
              <p>{item}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Future Enhancements</h2>
          <p>Next steps once the core system is fully deployed.</p>
        </div>
        <div className="chip-grid">
          {futures.map((item) => (
            <span key={item} className="chip ghost">
              {item}
            </span>
          ))}
        </div>
      </section>

      <section className="finale">
        <div>
          <h2>Experience the intelligent scheduler</h2>
          <p>
            Built to replace manual timetables with agentic allocation, auditability, and
            real-time flexibility.
          </p>
        </div>
        <div className="cta-row">
          <button type="button" className="btn primary" onClick={() => setView('signup')}>
            Create account
          </button>
          <button type="button" className="btn ghost" onClick={() => setView('login')}>
            Login
          </button>
        </div>
      </section>
    </div>
  )
}

export default App
