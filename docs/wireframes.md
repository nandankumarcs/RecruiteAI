# RecruiteAI — UI Wireframes & Component Specification

> **Last Updated:** 2026-05-06
> **UI Library:** shadcn/ui + Tailwind CSS v4
> **Theme:** Dark mode, deep navy/slate backgrounds, electric blue accents

---

## Design System

### Color Palette
```css
--background:      hsl(222, 47%, 6%)     /* Deep navy */
--card:            hsl(222, 40%, 10%)     /* Slightly lighter navy */
--card-hover:      hsl(222, 40%, 13%)     /* Card hover state */
--primary:         hsl(217, 91%, 60%)     /* Electric blue */
--primary-hover:   hsl(217, 91%, 50%)     /* Darker blue */
--accent:          hsl(262, 83%, 58%)     /* Purple accent */
--success:         hsl(142, 71%, 45%)     /* Green */
--warning:         hsl(38, 92%, 50%)      /* Amber */
--destructive:     hsl(0, 84%, 60%)       /* Red */
--muted:           hsl(215, 20%, 55%)     /* Gray text */
--border:          hsl(217, 33%, 17%)     /* Subtle border */
--text:            hsl(210, 40%, 98%)     /* White text */
--text-secondary:  hsl(215, 20%, 65%)     /* Secondary text */
```

### Typography
- **Font**: Inter (Google Fonts)
- **Headings**: font-semibold
- **Body**: font-normal, text-sm (14px)

### Shared shadcn Components Used
```
Button, Card, Dialog, Input, Textarea, Label, Badge,
Table, DropdownMenu, Sheet, Skeleton, Separator,
Tabs, Toast (sonner), Avatar, ScrollArea, Progress
```

---

## Page 1: Login Page (`/login`)

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│                                                                  │
│                    ┌─────────────────────────┐                   │
│                    │                         │                   │
│                    │    🎯 RecruiteAI        │                   │
│                    │    AI-Powered Recruiter  │                   │
│                    │                         │                   │
│                    │  ┌───────────────────┐  │                   │
│                    │  │ Email             │  │                   │
│                    │  └───────────────────┘  │                   │
│                    │  ┌───────────────────┐  │                   │
│                    │  │ Password          │  │                   │
│                    │  └───────────────────┘  │                   │
│                    │                         │                   │
│                    │  [    Sign In      ]    │                   │
│                    │                         │                   │
│                    └─────────────────────────┘                   │
│                                                                  │
│              Background: Subtle gradient animation               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**shadcn components**: Card, Input, Label, Button
**Behavior**:
- Centered card with glassmorphism effect
- Animated gradient background
- Form validation with error messages
- Redirects to `/dashboard` on success

---

## Page 2: Dashboard (`/dashboard`)

```
┌──────────────────────────────────────────────────────────────────┐
│ SIDEBAR          │  HEADER BAR                        [User ▼]  │
│                  │──────────────────────────────────────────────│
│ 🎯 RecruiteAI   │                                              │
│                  │  Dashboard                                   │
│ ────────────     │                                              │
│                  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──┐│
│ 📊 Dashboard     │  │ Active   │ │ Total    │ │ Calls    │ │Ca││
│                  │  │ Jobs     │ │Candidates│ │ Made     │ │Pe││
│ 💼 Jobs          │  │   12     │ │    87    │ │    34    │ │ 5││
│                  │  │ +3 week  │ │ +15 week │ │ +8 week  │ │  ││
│ 📞 Calls         │  └──────────┘ └──────────┘ └──────────┘ └──┘│
│                  │                                              │
│ ────────────     │  Recent Activity                             │
│                  │  ┌──────────────────────────────────────────┐│
│ ⚙️  Settings     │  │ 📞 Call completed with John Doe     2m  ││
│                  │  │ 📄 3 resumes uploaded to "Sr Eng"   15m ││
│ 🚪 Logout        │  │ 💼 New job created: "React Dev"     1h  ││
│                  │  │ ⭐ Call scored: 8.5/10 Jane Smith   2h  ││
│                  │  │ 📞 Call started with Mike Johnson   3h  ││
│                  │  └──────────────────────────────────────────┘│
│                  │                                              │
│                  │  Recent Jobs                 [View All →]    │
│                  │  ┌────────┐ ┌────────┐ ┌────────┐           │
│                  │  │Sr Eng  │ │React   │ │Backend │           │
│                  │  │5 cands │ │3 cands │ │8 cands │           │
│                  │  │2 calls │ │1 call  │ │4 calls │           │
│                  │  │Active● │ │Active● │ │Paused○ │           │
│                  │  └────────┘ └────────┘ └────────┘           │
└──────────────────┴──────────────────────────────────────────────┘
```

**shadcn components**: Card, Badge, ScrollArea, Separator, Avatar
**Stats cards**: Animated count-up, subtle gradient borders, icon + delta indicator
**Activity feed**: ScrollArea with timestamp badges
**Recent jobs**: Clickable cards → navigate to job detail

---

## Page 3: Jobs Page (`/jobs`)

```
┌──────────────────────────────────────────────────────────────────┐
│ SIDEBAR          │  HEADER BAR                        [User ▼]  │
│                  │──────────────────────────────────────────────│
│                  │                                              │
│                  │  Jobs                  [+ Create Job]        │
│                  │                                              │
│                  │  ┌─ Search ──────────┐  [Active▼] [Sort▼]   │
│                  │  └──────────────────-┘                       │
│                  │                                              │
│                  │  ┌──────────────────────────────────────────┐│
│                  │  │ TABLE                                    ││
│                  │  │ Title      │ Status │ Cands │ Calls│ Act ││
│                  │  │────────────┼────────┼───────┼──────┼─────││
│                  │  │ Sr. Eng    │●Active │  12   │  5   │ ⋮  ││
│                  │  │ React Dev  │●Active │   4   │  2   │ ⋮  ││
│                  │  │ Backend    │○Paused │   8   │  4   │ ⋮  ││
│                  │  │ QA Lead    │●Active │   3   │  0   │ ⋮  ││
│                  │  │ DevOps     │◆Closed │  15   │ 10   │ ⋮  ││
│                  │  └──────────────────────────────────────────┘│
│                  │                                              │
│                  │  Showing 1-5 of 12       [← 1 2 3 →]       │
│                  │                                              │
└──────────────────┴──────────────────────────────────────────────┘
```

### Create Job Dialog (Modal)
```
┌─────────────────────────────────────┐
│  Create New Job                  ✕  │
│─────────────────────────────────────│
│                                     │
│  Job Title *                        │
│  ┌─────────────────────────────┐    │
│  │ Senior Software Engineer    │    │
│  └─────────────────────────────┘    │
│                                     │
│  Job Description *                  │
│  ┌─────────────────────────────┐    │
│  │ We are looking for a senior │    │
│  │ engineer with 5+ years of   │    │
│  │ experience in...            │    │
│  │                             │    │
│  └─────────────────────────────┘    │
│                                     │
│  Requirements                       │
│  ┌─────────────────────────────┐    │
│  │ • React, TypeScript         │    │
│  │ • System design experience  │    │
│  │ • CI/CD knowledge           │    │
│  └─────────────────────────────┘    │
│                                     │
│         [Cancel]  [Create Job]      │
└─────────────────────────────────────┘
```

**shadcn components**: Table, Button, Dialog, Input, Textarea, Label, Badge, DropdownMenu
**Behavior**:
- Click row → navigate to `/jobs/{id}`
- ⋮ menu: Edit, Pause/Resume, Delete
- Search filters by title
- Status filter dropdown

---

## Page 4: Job Detail Page (`/jobs/:id`)

```
┌──────────────────────────────────────────────────────────────────┐
│ SIDEBAR          │  HEADER BAR                        [User ▼]  │
│                  │──────────────────────────────────────────────│
│                  │                                              │
│                  │  [← Back] Sr. Software Engineer    ●Active  │
│                  │                                              │
│                  │  TABS: [Resumes] [Calls] [Details]          │
│                  │  ═══════                                     │
│                  │                                              │
│                  │  ┌─────────────────────────────────────────┐ │
│                  │  │        RESUME UPLOAD ZONE               │ │
│                  │  │                                         │ │
│                  │  │   📁 Drag & drop resumes here           │ │
│                  │  │   or click to browse                    │ │
│                  │  │   Supports PDF, DOCX                    │ │
│                  │  │                                         │ │
│                  │  └─────────────────────────────────────────┘ │
│                  │                                              │
│                  │  Candidates (12)                             │
│                  │  ┌────────────────────────────────────────┐  │
│                  │  │ Name       │Phone      │Status│ Action │  │
│                  │  │────────────┼───────────┼──────┼────────│  │
│                  │  │ John Doe   │+1 555-123 │●Done │[View]  │  │
│                  │  │ Jane Smith │+1 555-456 │○Ready│[📞Call]│  │
│                  │  │ Mike J.    │+1 555-789 │⏳Busy│ —      │  │
│                  │  │ Sarah K.   │ (parsing) │○Upld │ —      │  │
│                  │  └────────────────────────────────────────┘  │
│                  │                                              │
└──────────────────┴──────────────────────────────────────────────┘
```

### [Calls] Tab View
```
│                  │  Call History                                │
│                  │  ┌────────────────────────────────────────┐  │
│                  │  │ Candidate │ Score │Duration│Status│View│  │
│                  │  │───────────┼───────┼────────┼──────┼────│  │
│                  │  │ John Doe  │ 8.5   │ 12:30  │✅Done│ → │  │
│                  │  │ Jane S.   │ 7.2   │ 10:15  │✅Done│ → │  │
│                  │  │ Mike J.   │  —    │  —     │⏳Prog│ — │  │
│                  │  └────────────────────────────────────────┘  │
```

### [Details] Tab View
```
│                  │  Job Information                    [Edit]   │
│                  │                                              │
│                  │  Title: Sr. Software Engineer                │
│                  │                                              │
│                  │  Description:                                │
│                  │  We are looking for a senior engineer...     │
│                  │                                              │
│                  │  Requirements:                               │
│                  │  • React, TypeScript                         │
│                  │  • System design experience                  │
│                  │  • CI/CD knowledge                           │
```

**shadcn components**: Tabs, Table, Badge, Button, Card, Sheet (for resume detail)
**Behavior**:
- Drag & drop resumes → auto-upload → parsing → display parsed info
- "📞 Call" button: Only enabled when resume is parsed and no active call
- Click "View" → navigate to `/calls/{id}`
- Resume detail opens in Sheet (slide-over) panel

### Resume Detail Sheet (Slide-over)
```
┌──────────────────────────────────────┐
│  Resume: John Doe               ✕   │
│──────────────────────────────────────│
│                                      │
│  📧 john.doe@email.com              │
│  📱 +1 555-123-4567                 │
│                                      │
│  Skills                              │
│  [React] [TypeScript] [Node.js]      │
│  [PostgreSQL] [AWS] [Docker]         │
│                                      │
│  Experience                          │
│  • Sr. Engineer @ Acme (3y)         │
│  • Engineer @ Startup (2y)          │
│                                      │
│  Education                           │
│  • B.S. Computer Science, MIT       │
│                                      │
│  ────────────────────────────────    │
│  Status: ● Parsed                    │
│  Uploaded: May 5, 2026              │
│                                      │
│         [📞 Start Interview Call]    │
└──────────────────────────────────────┘
```

---

## Page 5: Call Detail Page (`/calls/:id`)

```
┌──────────────────────────────────────────────────────────────────┐
│ SIDEBAR          │  HEADER BAR                        [User ▼]  │
│                  │──────────────────────────────────────────────│
│                  │                                              │
│                  │  [← Back to Job]  Call: John Doe    ✅Done  │
│                  │                                              │
│                  │  ┌───────────────────┐ ┌───────────────────┐ │
│                  │  │ Duration          │ │ Overall Score     │ │
│                  │  │ 12m 30s           │ │ ⭐ 8.5 / 10      │ │
│                  │  └───────────────────┘ └───────────────────┘ │
│                  │                                              │
│                  │  AI Evaluation                               │
│                  │  ┌──────────────────────────────────────────┐│
│                  │  │ Technical    ████████░░  8/10            ││
│                  │  │ Communication████████░░  8/10            ││
│                  │  │ Experience   ███████░░░  7/10            ││
│                  │  │ Problem Solv.█████████░  9/10            ││
│                  │  │                                          ││
│                  │  │ Remarks:                                 ││
│                  │  │ Strong candidate with excellent React    ││
│                  │  │ knowledge. Demonstrated clear thinking   ││
│                  │  │ in system design. Could improve on...    ││
│                  │  │                                          ││
│                  │  │ ✅ Strengths    ⚠️ Areas to Improve     ││
│                  │  │ • Deep React    • SQL optimization      ││
│                  │  │ • System design • Testing practices      ││
│                  │  │ • Communication                         ││
│                  │  └──────────────────────────────────────────┘│
│                  │                                              │
│                  │  Transcript                                  │
│                  │  ┌──────────────────────────────────────────┐│
│                  │  │ 🤖 AI: Hello John, thank you for       ││
│                  │  │ taking the time. I'm calling regarding  ││
│                  │  │ the Senior Engineer position at...      ││
│                  │  │                                          ││
│                  │  │ 👤 John: Hi, yes I'm very interested    ││
│                  │  │ in the role. I've been working with...  ││
│                  │  │                                          ││
│                  │  │ 🤖 AI: Great! Can you tell me about    ││
│                  │  │ your experience with React and...       ││
│                  │  │                                          ││
│                  │  │ 👤 John: Sure, I've been working with  ││
│                  │  │ React for about 4 years now...          ││
│                  │  └──────────────────────────────────────────┘│
│                  │                                              │
│                  │  🔊 [▶ Play Recording ━━━━━━━━━━━━━ 12:30] │
│                  │                                              │
└──────────────────┴──────────────────────────────────────────────┘
```

**shadcn components**: Card, Progress, Badge, ScrollArea, Separator, Tabs
**Behavior**:
- Score bars animated on mount
- Transcript auto-scrolls, speaker labels color-coded
- Audio player for recording playback
- During active call: shows live status + real-time transcript

### Live Call State (during active call)
```
│                  │  ┌──────────────────────────────────────────┐│
│                  │  │          📞 Call In Progress             ││
│                  │  │                                          ││
│                  │  │     ●●● Ringing +1 555-123-4567         ││
│                  │  │       (or) 🎙️ Connected — 02:34        ││
│                  │  │                                          ││
│                  │  │     Live Transcript:                     ││
│                  │  │     🤖 AI: Tell me about your...        ││
│                  │  │     👤 Candidate: Well, I have...       ││
│                  │  │                                          ││
│                  │  └──────────────────────────────────────────┘│
```

---

## Sidebar Component Detail

```
┌──────────────────┐
│                  │
│  🎯 RecruiteAI   │  Logo + brand name
│                  │
│  ────────────    │  Separator
│                  │
│  📊 Dashboard    │  NavLink (active: bg highlight + left border)
│  💼 Jobs         │  NavLink
│  📞 Calls        │  NavLink (shows all calls across jobs)
│                  │
│  ────────────    │  Separator
│                  │
│  ⚙️  Settings    │  NavLink
│                  │
│                  │
│  ────────────    │  Separator (at bottom)
│  👤 Dinesh T.    │  User avatar + name
│  🚪 Logout       │  Logout button
│                  │
└──────────────────┘
Width: 240px (collapsible to 64px on smaller screens)
```

---

## Responsive Behavior

| Breakpoint | Sidebar | Layout |
|---|---|---|
| ≥1280px (xl) | Full sidebar (240px) | Multi-column cards |
| ≥768px (md) | Collapsed sidebar (64px, icons only) | Stacked layout |
| <768px (sm) | Hidden (hamburger menu → Sheet) | Full-width mobile |

---

## Micro-Animations

1. **Stats cards**: Count-up animation on mount (0 → actual value over 600ms)
2. **Card hover**: translateY(-2px) + shadow increase (150ms ease)
3. **Page transitions**: Fade-in (200ms)
4. **Call status**: Pulsing dot animation for "in progress"
5. **Upload zone**: Border dash animation on drag-over
6. **Score bars**: Width animation from 0% → score% (800ms ease-out)
7. **Toast notifications**: Slide-in from top-right
8. **Table rows**: Subtle highlight on hover (100ms)
