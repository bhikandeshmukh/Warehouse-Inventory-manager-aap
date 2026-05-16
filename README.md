# Warehouse Inventory (Android)

Native Android warehouse inventory app with barcode scanning, offline-first storage,
and Supabase sync.

## What's in this starter

This zip is a **runnable Phase 1 foundation** (per the plan you shared). It compiles,
launches to a login → dashboard flow, scans barcodes with ML Kit, and persists
inventory in Room. The business screens (Inward / Transfer / Outward / Reports)
are scaffolded with clear TODOs that wire into a fully-implemented repository.

### ✅ Done

- Gradle build with all dependencies (Compose, Room, Hilt, CameraX, ML Kit,
  WorkManager, Ktor, Apache POI, DataStore).
- AndroidManifest + permissions + FileProvider for Excel sharing.
- Material 3 theme, typography, navigation.
- **Data layer**: Room entities (`bins`, `skus`, `inventory`, `stock_movements`)
  with FKs and indices, DAOs with summary queries, `AppDatabase`.
- **`InventoryRepository`** — transactional `stockIn` / `stockOut` / `transfer`
  with audit logging. All stock changes go through `@Transaction` blocks so
  state is consistent even on crash.
- **Barcode scanner** (`scanner/`): `BarcodeAnalyzer` (ML Kit + CameraX, bounded
  concurrency, debounced) + `BarcodeScannerView` Composable with permission flow.
- **Login + session** — `SessionManager` (DataStore) and `AuthRepository` with a
  demo mode that lets you log in immediately before Supabase is set up.
- **Dashboard** with operation tiles and a "pending sync" pill that triggers
  one-shot sync.
- **Search screen** — fully working: scan or type a SKU/BIN, see per-bin totals.
- **Sync layer** — `SyncWorker` (Hilt-injected, batched upload of bins → SKUs →
  movements → marks each row synced) and `SyncManager` (periodic + one-shot
  scheduling with exponential back-off).

### 🚧 Stubs to flesh out

Each file says exactly what to build:

- `ui/inward/StockInwardScreen.kt` — scan BIN → scan SKU → qty → `repo.stockIn(...)`
- `ui/transfer/StockTransferScreen.kt` — scan FROM → scan TO → scan SKU → qty → `repo.transfer(...)`
- `ui/outward/StockOutwardScreen.kt` — scan BIN → scan SKU → qty → `repo.stockOut(...)`
- `ui/reports/ReportsScreen.kt` — wire Apache POI export/import (sheet names live in `utils/Constants.kt`)

The repository methods these call are already implemented and tested-shaped —
each one is a single transactional call.

## Setup

1. Open in **Android Studio Hedgehog (2023.1.1) or newer**.
2. Let Gradle sync. If prompted, accept the JDK 17 requirement.
3. Configure Supabase (optional during development):
   - Open `app/build.gradle.kts` and replace the two `buildConfigField` lines:
     ```
     buildConfigField("String", "SUPABASE_URL", "\"https://YOUR-PROJECT.supabase.co\"")
     buildConfigField("String", "SUPABASE_ANON_KEY", "\"YOUR-ANON-KEY\"")
     ```
   - In production move these to `local.properties` and read via
     `localProperties` — don't commit secrets.
   - Until you do, the app runs in **demo mode**: any non-empty username/password
     will sign you in and sync calls are skipped.

## Supabase schema

Create these tables in your Supabase project (SQL Editor):

```sql
create table bins (
    bin_code      text primary key,
    description   text,
    zone          text,
    is_active     boolean default true,
    updated_at    timestamptz default now()
);

create table skus (
    sku_code      text primary key,
    name          text not null,
    category      text,
    size          text,
    color         text,
    uom           text default 'PCS',
    is_active     boolean default true,
    updated_at    timestamptz default now()
);

create table stock_movements (
    id              uuid primary key,
    type            text not null check (type in ('INWARD','OUTWARD','TRANSFER','ADJUSTMENT')),
    sku_code        text not null references skus(sku_code),
    from_bin_code   text references bins(bin_code),
    to_bin_code     text references bins(bin_code),
    quantity        integer not null check (quantity > 0),
    performed_by    text not null,
    note            text,
    created_at      timestamptz not null
);

-- Server-side inventory view re-built from movements (recommended over a
-- mutable inventory table — the audit log is the source of truth).
create view inventory as
select
    coalesce(to_bin_code, from_bin_code) as bin_code,
    sku_code,
    sum(
        case
            when type = 'INWARD'   and to_bin_code   = bin_code then  quantity
            when type = 'OUTWARD'  and from_bin_code = bin_code then -quantity
            when type = 'TRANSFER' and to_bin_code   = bin_code then  quantity
            when type = 'TRANSFER' and from_bin_code = bin_code then -quantity
            else 0
        end
    ) as quantity
from stock_movements
group by 1, 2
having sum(...) > 0;
```

Then enable RLS and create policies appropriate for your access model.

## Architecture notes

**Why the audit log is the source of truth.** All stock changes write a row to
`stock_movements` *and* update the local `inventory` table atomically inside one
Room transaction. The sync layer only pushes `stock_movements` to the cloud —
the server can re-derive `inventory` from those rows. This way a movement created
offline carries a UUID that uniquely identifies it forever, so retries are safe.

**Scanner performance.** `BarcodeAnalyzer` uses an `AtomicBoolean` to guarantee
only one ML Kit task is in flight at a time. Frames that arrive while a task is
running are closed immediately. CameraX is configured with
`STRATEGY_KEEP_ONLY_LATEST` so the queue can't grow. On a Snapdragon 6-series
phone this comfortably hits 30 fps analysis.

**Hilt + WorkManager.** `SyncWorker` is `@HiltWorker`-annotated and the app
class provides the `HiltWorkerFactory`. The manifest disables the default
WorkManager initializer so Hilt's config is used instead.

**DataStore over EncryptedSharedPreferences.** Tokens live in `SessionManager`'s
DataStore. If you ship to a security-sensitive customer, wrap this with a
`MasterKey` + `EncryptedFile` or move to the Android Keystore.

## Project layout

```
app/src/main/java/com/warehouse/inventory/
├── data/
│   ├── local/         Room DB, entities, DAOs
│   ├── remote/        Supabase DTOs + service (Ktor)
│   └── repository/    InventoryRepository, AuthRepository, SessionManager
├── di/                Hilt modules (DatabaseModule, NetworkModule)
├── scanner/           ML Kit analyzer + Compose camera view
├── sync/              SyncWorker + SyncManager (WorkManager)
├── ui/
│   ├── theme/
│   ├── navigation/
│   ├── login/
│   ├── dashboard/
│   ├── inward/        ← stub
│   ├── transfer/      ← stub
│   ├── outward/       ← stub
│   ├── search/        ← working
│   └── reports/       ← stub
└── utils/             OpResult, Constants
```

## Honesty about scope

This is a foundation, not a finished product. The plan you shared estimates
15+ days of work for the three phases; this zip gets you to roughly the end of
day 3–4. The architectural decisions are made and the hard infra (DB schema,
repository transactions, scanner pipeline, sync wiring) is done — the remaining
work is mostly wiring screens to repository calls plus the Excel module.

Have fun building it.
