# Afterlife Neogenesis Unified Product Blueprint

## 1. Product definition

Afterlife Neogenesis is a persistent digital universe built on top of NeoGen, an AI operating system. The public website, player dashboard, avatar forge, companion system, marketplace, wallet, creator tools, and future RPG world are one connected platform rather than disconnected prototypes.

NeoGen provides the intelligence, permissions, memory, workflows, events, plugins, governance, and model routing. Afterlife Neogenesis provides the player-facing universe and product experience. `acoin` remains a separate economy service and integrates with NeoGen through a permissioned API and plugin boundary.

## 2. Core principles

1. Persistent universe: player identity, companions, assets, history, and world state persist over time.
2. Governance first: privileged actions require explicit scopes, audit events, and approval when risk is high.
3. AI as an active participant: agents can plan, research, build, test, document, organize, and recommend, but high-impact actions remain user controlled.
4. Service boundaries: AI orchestration, game systems, marketplace, identity, storage, and economy remain independently testable.
5. Web platform first: establish a reliable public site and authenticated dashboard before expanding into a large RPG client.
6. No false previews: a preview is only described as live when a real deployment or verified local runtime exists.

## 3. User experience

### Public landing page

The landing page presents:

- AFTERLIFE NEOGENESIS branding
- The Persistent Digital Universe positioning
- Launch App and Explore Universe actions
- AI Companion, NFT Avatar Forge, Marketplace, and Wallet feature pillars
- Login and Join entry points

### Authenticated dashboard

The dashboard contains:

- Navigation: Avatar, Pets, Collection, Marketplace, Wallet, Guilds, Quests, Settings
- Main 3D avatar preview
- Persistent AI Assistant chat
- Alerts, approvals, rewards, active quests, and recent activity
- Responsive layouts for desktop, tablet, and mobile

### Avatar Forge

The Avatar Forge supports:

- 3D avatar viewer
- Drag-and-drop equipment
- AI-generated cosmetic concepts
- 100 rarity and evolution tiers
- Collectible mint preview
- Equipment statistics
- Evolution tree
- Save, load, duplicate, and version designs
- User approval before minting, listing, purchasing, or spending currency

### Marketplace

The marketplace supports:

- Fixed-price listings
- Auction house
- Creator store
- Featured collections
- Trading history
- Search, filters, watchlists, and collection pages
- Fraud, provenance, and risk indicators
- Permission-gated purchase and listing actions

### Wallet

The wallet shows:

- Afterlife Coin balance
- Transaction history
- Marketplace purchases
- Collectible inventory
- Rewards
- Optional staking only after legal, security, economic, and technical review

### AI Companion

Each player begins with an AI companion that can:

- Explain mechanics and lore
- Suggest builds and quests
- Help design avatars
- Organize inventory
- Recommend trades without executing them silently
- Summarize world events
- Answer questions about the universe
- Remember user-approved preferences
- Route specialized tasks to NeoGen agents

The companion must clearly distinguish suggestions from completed actions.

## 4. Site map

Public:

- Home
- About
- Lore
- Roadmap
- Download
- Marketplace
- Avatar Forge
- NFT Collection
- Companions
- Guilds
- Leaderboards
- Events
- Support
- FAQ
- Privacy
- Terms

Authenticated:

- Dashboard
- Avatar
- Pets
- Collection
- Marketplace
- Wallet
- Guilds
- Quests
- Events
- AI Companion
- Notifications
- Approvals
- Settings

Creator and developer:

- Creator Hub
- Developer Portal
- API documentation
- Plugin documentation
- Asset submission
- Analytics
- Revenue and payout reporting

## 5. Unified architecture

```text
Web and Mobile Clients
        |
        v
API Gateway / Backend-for-Frontend
        |
        +-------------------------------+
        |                               |
        v                               v
Afterlife Product Services          NeoGen AI Kernel
- Identity                          - Agent Manager
- Player Profile                    - Memory Engine
- Avatar Forge                      - Permission Manager
- Companion                         - Model Router
- Inventory                         - Workflow Engine
- Marketplace                       - Plugin Manager
- Guilds and Quests                 - Event Bus
- Lore and World State              - Project Intelligence
        |                               |
        +---------------+---------------+
                        |
                        v
              Shared Platform Services
              - PostgreSQL
              - Object Storage
              - Realtime Gateway
              - Search / Semantic Index
              - Audit Log
              - Notifications
                        |
                        v
                   Acoin Service
              - Accounts and Wallets
              - Ledger
              - Transactions
              - Rewards
              - Marketplace Settlement
```

## 6. NeoGen AI operating system

### AI Kernel

The AI Kernel is the orchestration and policy core. It coordinates:

- Agents
- Memory
- Permissions
- Context
- Models
- Workflows
- Events
- Plugins
- Scheduling
- Human approvals

### Memory Engine

Memory domains:

- Session
- User
- Project
- Workspace
- Team
- Knowledge
- Documents
- Code
- Game state
- Companion
- Semantic index

Every memory record includes:

- UUID
- Domain
- Tags
- Importance
- Source
- Created and updated timestamps
- Confidence
- Relationships
- Version history
- Owner and visibility
- Retention policy
- Permission requirements

### Event system

Everything important emits an event, including:

- File created or deleted
- Git commit
- Terminal started
- AI response generated
- Permission granted or denied
- Memory updated
- Workflow completed or failed
- Plugin installed or disabled
- Avatar saved
- Item minted
- Listing created
- Purchase requested
- Transaction settled
- Quest completed

Events power automation, audit logs, dashboards, notifications, analytics, and learning.

### Agent Center

Standard agents include:

- Planner
- Coding
- Research
- Documentation
- Terminal
- Security
- Testing
- Deployment
- Database
- UI Designer
- Governance
- Marketplace Risk
- Lore
- Quest Design

Each agent exposes:

- Name and identity
- Status
- Current task
- Permissions
- Memory usage
- Execution time
- Cost
- Logs
- Queue
- Capabilities
- Risk level

### Workflow Engine

Workflows connect triggers, agents, tools, approvals, and actions.

Example development workflow:

```text
Trigger -> Research -> Code -> Test -> Security Review -> Documentation -> Approval -> Deploy
```

Example marketplace workflow:

```text
Listing Request -> Validate Ownership -> Risk Check -> Fee Quote -> User Approval -> Publish Listing
```

### Model Router

The Model Router selects providers using:

- Task type
- Capability
- Cost
- Latency
- Privacy requirement
- Context size
- Availability
- User or organization policy

It supports automatic routing, usage analytics, failover, context optimization, and local-model preference for offline or private work.

### Governance Dashboard

The governance dashboard displays:

- Active permissions
- Pending approvals
- Running agents
- Model usage
- Audit events
- Risk level
- Active workflows
- Installed plugins
- Recent automations
- Security alerts
- Marketplace and wallet risk events

## 7. Recommended technology stack

Frontend:

- Next.js
- React
- TypeScript
- Tailwind CSS
- Framer Motion
- React Three Fiber

Backend:

- FastAPI and Python
- PostgreSQL
- SQLAlchemy and Alembic
- Redis for queues, caching, and ephemeral coordination
- WebSockets or a managed realtime service
- S3-compatible object storage

Authentication:

- Auth.js or Clerk for the web application
- OAuth/OIDC support for enterprise later

Payments:

- Stripe for fiat payments where legally and operationally appropriate

AI:

- Provider adapters behind the NeoGen Model Router
- Local model adapters as plugins
- Retrieval and semantic search through the Memory Engine

Economy:

- Separate `acoin` service
- Double-entry ledger
- Idempotent transaction APIs
- Signed service-to-service requests
- No direct balance mutation from the frontend

Blockchain and collectibles:

- Optional and isolated behind an adapter
- Do not require blockchain for the first usable release
- Provide a conventional database-backed collectible system first

## 8. Repository responsibilities

### `tonematrix689-hash/NeoGen`

Owns:

- AI Kernel
- Product backend
- Public web application
- Authenticated dashboard
- Avatar Forge
- Companion system
- Marketplace orchestration
- Inventory and collections
- Guilds, quests, lore, and world state
- Plugin SDK
- Governance and approval systems

Suggested future layout:

```text
apps/
  web/
  api/
  worker/
packages/
  ui/
  contracts/
  sdk/
genesis/
  app/kernel/
  services/agents/
  services/memory/
  services/permissions/
  services/models/
  services/workflows/
  services/plugins/
  services/projects/
  domains/afterlife/
docs/
infra/
tests/
```

### `tonematrix689-hash/acoin`

Owns:

- Wallet accounts
- Double-entry ledger
- Transaction posting
- Rewards
- Settlement
- Balance queries
- Reconciliation
- Audit exports
- Economy administration

Acoin must not own avatar, marketplace presentation, or AI orchestration logic.

## 9. Delivery roadmap

### Phase A: Foundation

- Merge and stabilize kernel runtime changes
- Establish architecture decision records
- Add CI, formatting, typing, tests, and security scanning
- Define shared API contracts
- Create environment and secrets documentation

### Phase B: Public platform

- Landing page
- About, Lore, Roadmap, FAQ, Privacy, and Terms
- Authentication
- Base design system
- Real hosted preview with deployment checks

### Phase C: Dashboard and companion

- Authenticated shell
- Navigation and profile
- AI Companion chat
- Memory preferences
- Permission prompts
- Notification and approval center

### Phase D: Avatar Forge and inventory

- 3D viewer
- Equipment system
- Design persistence
- Evolution and rarity model
- Inventory and collection pages
- AI cosmetic ideation

### Phase E: Marketplace and Acoin

- Acoin ledger service
- Wallet UI
- Listings and auctions
- Settlement workflow
- Creator store
- Transaction history

### Phase F: Intelligence and automation

- Agent Center
- Workflow builder
- Project intelligence
- Model routing
- Plugin manager and marketplace
- Governance dashboard

### Phase G: World and RPG

- Quests
- Guilds
- Events
- Persistent world state
- Companion progression
- Mobile clients
- Creator tools and public API

## 10. First production milestone

The first credible release is not the complete RPG. It is a hosted web platform containing:

1. Public landing page and core information pages.
2. Authentication and player profiles.
3. Dashboard with a functioning AI Companion.
4. Avatar design records and a basic 3D preview.
5. Inventory and collection pages.
6. Permission and approval center.
7. Audited NeoGen events.
8. Deployment, tests, and operational documentation.

Marketplace settlement, blockchain adapters, staking, and autonomous deployment remain behind later milestones and explicit risk review.

## 11. Definition of done

A feature is complete only when:

- It runs in a reproducible environment.
- Automated tests cover its critical behavior.
- Permissions and audit events are defined.
- User-visible errors are handled.
- Documentation is updated.
- Security implications are reviewed.
- A real preview or deployment is verified before it is described as live.
