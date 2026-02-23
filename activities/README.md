# Activities Module - Dynamic Template System

## Table of Contents
- [Overview](#overview)
- [Architecture Diagram](#architecture-diagram)
- [Data Model](#data-model)
- [Frontend Pages Flow](#frontend-pages-flow)
- [API Endpoints](#api-endpoints)
- [User Workflows](#user-workflows)

---

## Overview

The **Activities Module** is a dynamic spreadsheet-like system that allows administrators to create activity templates with customizable columns, and users to fill in activities based on those templates. It supports:

- **Admin-managed column definitions** (text, number, date, email, phone, boolean, select)
- **Templates with customizable column configurations**
- **Department-based organization** (Phase 1: single default department)
- **Activity submission workflow** (draft → submitted)
- **Dashboard KPIs and analytics**
- **File attachments per activity row**
- **Excel import/export**

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ACTIVITIES SYSTEM ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────────┐
                              │      DEPARTMENT      │
                              │   (القسم العام)       │
                              │                      │
                              │ • name               │
                              │ • code (e.g., 'ALL') │
                              │ • is_default = True  │
                              └──────────┬───────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
                    ▼                    ▼                    ▼
        ┌───────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
        │   ACTIVITY        │  │   ACTIVITY      │  │   ACTIVITY          │
        │   TEMPLATE 1      │  │   TEMPLATE 2    │  │   TEMPLATE N        │
        │   (نموذج الأنشطة)  │  │   (Published)   │  │   (Draft/Archived)  │
        │                   │  │                 │  │                     │
        │ • name            │  │ • name          │  │ • name              │
        │ • description     │  │ • description   │  │ • description       │
        │ • status          │  │ • notes         │  │ • status            │
        │ • is_active_title │  │ • header_image  │  │ • is_deleted        │
        │ • owner           │  │                 │  │                     │
        └────────┬──────────┘  └────────┬────────┘  └─────────────────────┘
                 │                      │
                 │    ┌─────────────────┴───────────────────────┐
                 │    │                                         │
                 ▼    ▼                                         ▼
    ┌─────────────────────────┐                    ┌─────────────────────────┐
    │  TEMPLATE COLUMNS       │                    │   COLUMN DEFINITIONS    │
    │  (Per-Template Config)  │───────────────────▶│   (Admin-Managed)       │
    │                         │                    │                         │
    │ • order                 │                    │ • key (unique)          │
    │ • width                 │                    │ • label                 │
    │ • is_required           │                    │ • data_type             │
    │ • is_visible            │                    │ • options (for select)  │
    │                         │                    │ • allows_attachment     │
    └────────┬────────────────┘                    │ • is_system             │
             │                                     └─────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                     ACTIVITY SHEETS (Per User)                   │
    │                                                                  │
    │  ┌─────────────────────┐   ┌─────────────────────┐              │
    │  │  USER A's SHEET     │   │  USER B's SHEET     │              │
    │  │                     │   │                     │              │
    │  │ • name              │   │ • name              │              │
    │  │ • template_id       │   │ • template_id       │              │
    │  │ • owner             │   │ • owner             │              │
    │  │ • department        │   │ • department        │              │
    │  │ • is_submitted      │   │ • is_submitted      │              │
    │  │ • column_snapshot   │   │ • column_snapshot   │              │
    │  └─────────┬───────────┘   └─────────┬───────────┘              │
    │            │                         │                          │
    │            ▼                         ▼                          │
    │  ┌─────────────────────┐   ┌─────────────────────┐              │
    │  │   SHEET ROWS        │   │   SHEET ROWS        │              │
    │  │   (Activities)      │   │   (Activities)      │              │
    │  │                     │   │                     │              │
    │  │ • row_order         │   │ • row_order         │              │
    │  │ • data (JSON)       │   │ • data (JSON)       │              │
    │  │ • styles (JSON)     │   │ • styles (JSON)     │              │
    │  │ • activity_status   │   │ • activity_status   │              │
    │  │ • is_submitted      │   │ • is_submitted      │              │
    │  │ • attachments[]     │   │ • attachments[]     │              │
    │  └─────────────────────┘   └─────────────────────┘              │
    │                                                                  │
    └─────────────────────────────────────────────────────────────────┘
```

---

## Data Model

### Entity Relationship Diagram

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           DATABASE ENTITIES                                     │
└────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐        ┌─────────────────────────┐
│     Department      │        │  ActivityColumnDef      │
├─────────────────────┤        ├─────────────────────────┤
│ id (PK)             │        │ id (PK)                 │
│ name                │        │ key (unique)            │
│ code (unique)       │        │ label                   │
│ description         │        │ data_type               │◄──────────┐
│ is_default          │        │ default_width           │           │
│ is_active           │        │ options (JSON)          │           │
│ created_at          │        │ allows_attachment       │           │
│ updated_at          │        │ attachment_required     │           │
└─────────┬───────────┘        │ is_system               │           │
          │                    │ is_active               │           │
          │                    └───────────┬─────────────┘           │
          │                                │                         │
          │                    ┌───────────▼─────────────┐           │
          │                    │ ActivityColValidation   │           │
          │                    ├─────────────────────────┤           │
          │                    │ id (PK)                 │           │
          │                    │ column_id (FK)          │           │
          │                    │ rule_type               │           │
          │                    │ rule_value              │           │
          │                    │ error_message           │           │
          │                    └─────────────────────────┘           │
          │                                                          │
          │                    ┌─────────────────────────┐           │
          │                    │   ActivityTemplate      │           │
          │                    ├─────────────────────────┤           │
          │                    │ id (PK)                 │           │
          │                    │ name                    │           │
          │                    │ description             │           │
          │                    │ notes                   │           │
          │ target_department ◄┤ target_department_id    │           │
          │                    │ owner_id (FK→User)      │           │
          │                    │ status (draft/pub/arch) │           │
          │                    │ is_active_title         │           │
          │                    │ is_deleted              │           │
          │                    │ header_image            │           │
          │                    │ published_at            │           │
          │                    └───────────┬─────────────┘           │
          │                                │                         │
          │                    ┌───────────▼─────────────┐           │
          │                    │ ActivityTemplateColumn  │           │
          │                    ├─────────────────────────┤           │
          │                    │ id (PK)                 │           │
          │                    │ template_id (FK)        │           │
          │                    │ column_def_id (FK)──────┼───────────┘
          │                    │ order                   │
          │                    │ width                   │
          │                    │ is_required             │
          │                    │ is_visible              │
          │                    └─────────────────────────┘
          │
          │                    ┌─────────────────────────┐
          │                    │    ActivitySheet        │
          │                    ├─────────────────────────┤
          │                    │ id (PK)                 │
          │                    │ name                    │
          │                    │ description             │
          │                    │ template_id (FK)        │
          │ department_id     ◄┤ department_id (FK)      │
          │                    │ owner_id (FK→User)      │
          │                    │ column_snapshot (JSON)  │
          │                    │ row_count               │
          │                    │ is_submitted            │
          │                    │ submitted_at            │
          │                    │ is_active               │
          │                    └───────────┬─────────────┘
          │                                │
          │                    ┌───────────▼─────────────┐
          │                    │   ActivitySheetRow      │
          │                    ├─────────────────────────┤
          │                    │ id (PK)                 │
          │                    │ sheet_id (FK)           │
          │                    │ row_order               │
          │                    │ data (JSON)             │
          │                    │ styles (JSON)           │
          │                    │ height                  │
          │                    │ activity_status         │
          │                    │ is_submitted            │
          │                    │ submitted_at            │
          │                    └───────────┬─────────────┘
          │                                │
          │                    ┌───────────▼─────────────┐
          │                    │ ActivityRowAttachment   │
          │                    ├─────────────────────────┤
          │                    │ id (PK)                 │
          │                    │ row_id (FK)             │
          │                    │ column_key              │
          │                    │ original_filename       │
          │                    │ file_size               │
          │                    │ mime_type               │
          │                    │ file_content (BLOB)     │
          │                    │ is_image                │
          │                    └─────────────────────────┘
```

### Activity Status Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    ACTIVITY STATUS WORKFLOW                      │
└─────────────────────────────────────────────────────────────────┘

  TEMPLATE STATUS:                      USER ACTIVITY STATUS:
  ================                      =====================
  
    ┌─────────┐                           ┌──────────────┐
    │  DRAFT  │                           │  NOT_STARTED │ ◄── Initial
    └────┬────┘                           │    (لم يبدأ)  │
         │                                └───────┬──────┘
         │ Admin Publishes                        │
         ▼                                        ▼
    ┌─────────────┐  Users can now       ┌──────────────┐
    │  PUBLISHED  │──────create─────────▶│  IN_PROGRESS │
    └──────┬──────┘    activities        │  (قيد التنفيذ) │
           │                             └───────┬──────┘
           │                                     │
           │ Admin Archives                      ▼
           ▼                             ┌──────────────┐
    ┌─────────────┐                      │   COMPLETED  │
    │  ARCHIVED   │                      │    (مكتمل)    │
    │ (read-only) │                      └──────────────┘
    └─────────────┘


  SUBMISSION FLOW:
  ================

    ┌─────────────┐       User Submits        ┌─────────────┐
    │    DRAFT    │ ─────────────────────────▶│  SUBMITTED  │
    │ (Editable)  │                           │ (Read-only) │
    └─────────────┘                           └─────────────┘
```

---

## Frontend Pages Flow

### Navigation Structure

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND NAVIGATION FLOW                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

                          ┌─────────────────────┐
                          │    HeaderMenu.vue    │
                          │                     │
                          │ [قائمة الأنشطة]      │ ◄── All Users
                          │ [إدارة نماذج الأنشطة] │ ◄── Admins Only
                          └──────────┬──────────┘
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           │                         │                         │
           ▼                         ▼                         ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│  /activities/local   │  │  /control/templates  │  │     /dashboard       │
│                      │  │                      │  │                      │
│ ListingActivities    │  │ TemplateManagement   │  │    Dashboard.vue     │
│      .vue            │  │      .vue            │  │                      │
│                      │  │                      │  │ • KPIs Overview      │
│ • Active Templates   │  │ • All Templates      │  │ • Charts             │
│ • User's Sheets      │  │ • Create/Edit/Delete │  │ • Programs List      │
│ • Spreadsheet View   │  │ • Publish/Archive    │  │                      │
└─────────┬────────────┘  └─────────┬────────────┘  └──────────┬───────────┘
          │                         │                          │
          │                         │                          │
          ▼                         ▼                          ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ /activities/local/:id│  │/control/templates/:id│  │/programs/details/:id │
│                      │  │     /activities      │  │                      │
│LocalActivitiesDetail │  │TemplateActivities    │  │ ProgramDetails.vue   │
│      .vue            │  │    Detail.vue        │  │                      │
│                      │  │                      │  │ • Template KPIs      │
│ • Activities List    │  │ • Users Tab          │  │ • By Department      │
│ • Card View          │  │ • Activities Tab     │  │ • Quarterly Charts   │
│ • Create/Edit/Delete │  │ • Export to Excel    │  │                      │
└─────────┬────────────┘  └──────────────────────┘  └──────────────────────┘
          │
          ├──────────────────────────────────────────┐
          │                                          │
          ▼                                          ▼
┌──────────────────────────┐            ┌──────────────────────────┐
│/activities/local/:id/    │            │/activities/local/:id/    │
│      create              │            │   activity/:activityId   │
│                          │            │                          │
│   CreateActivity.vue     │            │   ActivityDetails.vue    │
│                          │            │                          │
│ • Form with all columns  │            │ • Full Activity View     │
│ • Attachment upload      │            │ • All Column Values      │
│ • Save as draft          │            │ • Attachments Sidebar    │
└──────────────────────────┘            └──────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────┐
│                      DEPARTMENT ACTIVITIES PAGE                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

         Dashboard
             │
             │ Click Department Card
             ▼
┌──────────────────────────┐
│ /departments/:id/        │
│      activities          │
│                          │
│ DepartmentActivities.vue │
│                          │
│ • Department KPIs        │
│ • Status Donut Chart     │
│ • Weekly Trend Line      │
│ • Activities Cards       │
└──────────────────────────┘
```

### Page Components Breakdown

#### 1. ListingActivities.vue (`/activities/local`)
**Purpose**: Main entry point for users to view and manage their activities across all templates.

```
┌─────────────────────────────────────────────────────────────────┐
│                   ListingActivities.vue                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Active Templates Dropdown                               │    │
│  │  ▼ Select Template: [نموذج الأنشطة للسنة 2024]           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐     │
│  │  Sheet 1       │  │  Sheet 2       │  │  + Create New  │     │
│  │  (Submitted)   │  │  (Draft)       │  │    Sheet       │     │
│  └────────────────┘  └────────────────┘  └────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  SPREADSHEET VIEW (when sheet selected)                  │    │
│  │  ┌─────┬─────────┬─────────┬─────────┬─────────┐         │    │
│  │  │ #   │ النشاط  │ التاريخ │ الحالة  │ إجراءات │         │    │
│  │  ├─────┼─────────┼─────────┼─────────┼─────────┤         │    │
│  │  │  1  │ نشاط 1  │ 2024-01 │ مكتمل   │ ✏️ 🗑️   │         │    │
│  │  │  2  │ نشاط 2  │ 2024-02 │ قيد...  │ ✏️ 🗑️   │         │    │
│  │  └─────┴─────────┴─────────┴─────────┴─────────┘         │    │
│  │                                                           │    │
│  │  [Submit Sheet] [Export Excel] [Import Excel]             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**API Calls**:
- `GET /activities/titles/` - List published templates
- `GET /activities/user/activity-page/` - Get active title data
- `GET /activities/titles/:id/columns/` - Get template columns
- `POST /activities/user/templates/:id/activities/` - Create activity
- `PATCH /activities/user/activities/:id/` - Update activity
- `DELETE /activities/user/activities/:id/` - Delete activity

#### 2. LocalActivitiesDetail.vue (`/activities/local/:id`)
**Purpose**: View all user's activities for a specific template in card format.

```
┌─────────────────────────────────────────────────────────────────┐
│                  LocalActivitiesDetail.vue                       │
├─────────────────────────────────────────────────────────────────┤
│  [← رجوع]  Template Name: نموذج الأنشطة للسنة 2024              │
│                                                                  │
│  [+ إضافة نشاط جديد]                                             │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐     │
│  │  Activity Card │  │  Activity Card │  │  Activity Card │     │
│  │  ─────────────│  │  ─────────────│  │  ─────────────│     │
│  │  Title: نشاط 1│  │  Title: نشاط 2│  │  Title: نشاط 3│     │
│  │  Status: مكتمل│  │  Status: Draft │  │  Status: Draft │     │
│  │  Date: ...    │  │  Date: ...    │  │  Date: ...    │     │
│  │  [Edit][Del]  │  │  [Edit][Del]  │  │  [Edit][Del]  │     │
│  └────────────────┘  └────────────────┘  └────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  SIDE PANEL (on card click)                              │    │
│  │  • Activity Summary                                      │    │
│  │  • Key Fields Preview                                    │    │
│  │  • [View Full Details] [Edit]                            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**API Calls**:
- `GET /activities/user/templates/:id/activities/` - List activities
- `DELETE /activities/user/activities/:id/` - Delete activity

#### 3. ActivityDetails.vue (`/activities/local/:id/activity/:activityId`)
**Purpose**: Full detailed view of a single activity with all columns and attachments.

```
┌─────────────────────────────────────────────────────────────────┐
│                    ActivityDetails.vue                           │
├─────────────────────────────────────────────────────────────────┤
│  [← رجوع]  Activity Title                        [Edit Button]  │
│                                                                  │
│  ┌─────────────────────────┐  ┌────────────────────────────┐    │
│  │  MAIN CONTENT           │  │  ATTACHMENTS SIDEBAR       │    │
│  │                         │  │                            │    │
│  │  ┌─────────────────┐    │  │  📎 attachment1.pdf        │    │
│  │  │ Field 1: Value  │    │  │     [Download] [Preview]   │    │
│  │  └─────────────────┘    │  │                            │    │
│  │  ┌─────────────────┐    │  │  🖼️ image.jpg             │    │
│  │  │ Field 2: Value  │    │  │     [Download] [Preview]   │    │
│  │  └─────────────────┘    │  │                            │    │
│  │  ┌─────────────────┐    │  │                            │    │
│  │  │ Field N: Value  │    │  │                            │    │
│  │  └─────────────────┘    │  │                            │    │
│  │                         │  │                            │    │
│  │  Status: مكتمل          │  │                            │    │
│  │  Created: 2024-01-15    │  │                            │    │
│  │  Submitted: 2024-01-20  │  │                            │    │
│  └─────────────────────────┘  └────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**API Calls**:
- `GET /activities/user/activities/:id/` - Get activity details
- `GET /activities/attachments/:id/download/` - Download attachment
- `GET /activities/attachments/:id/preview/` - Preview image

#### 4. TemplateManagement.vue (`/control/templates`) - Admin Only
**Purpose**: Admin dashboard to manage all activity templates.

```
┌─────────────────────────────────────────────────────────────────┐
│                  TemplateManagement.vue (Admin)                  │
├─────────────────────────────────────────────────────────────────┤
│  إدارة النماذج                           [+ إنشاء قالب جديد]     │
│                                                                  │
│  ┌────────────────────────┐  ┌────────────────────────┐         │
│  │  Template Card         │  │  Template Card         │         │
│  │  ──────────────────    │  │  ──────────────────    │         │
│  │  📄 نموذج الأنشطة 2024  │  │  📄 نموذج الأنشطة 2025  │         │
│  │                        │  │                        │         │
│  │  Status: [نشط]         │  │  Status: [مسودة]       │         │
│  │                        │  │                        │         │
│  │  [⭐ Active] [✏️] [🗑️]  │  │  [📤 Publish] [✏️] [🗑️] │         │
│  └────────────────────────┘  └────────────────────────┘         │
│                                                                  │
│  ⭐ = Set as Active Title (users can add activities)             │
│  📤 = Publish (draft → published)                                │
│  ✏️ = Edit (draft only)                                          │
│  🗑️ = Delete/Archive                                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**API Calls**:
- `GET /activities/templates/` - List all templates
- `POST /activities/templates/` - Create template
- `PATCH /activities/templates/:id/` - Update template
- `DELETE /activities/templates/:id/` - Delete/archive
- `POST /activities/templates/:id/publish/` - Publish
- `POST /activities/titles/:id/set-active/` - Set as active title

#### 5. TemplateCreate.vue (`/control/templates/create` or `/control/templates/edit/:id`)
**Purpose**: Create or edit template structure with drag-and-drop column configuration.

```
┌─────────────────────────────────────────────────────────────────┐
│                    TemplateCreate.vue (Admin)                    │
├─────────────────────────────────────────────────────────────────┤
│  [← رجوع]  إنشاء نموذج جديد              [إلغاء] [إنشاء/تحديث]   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  TABS:  [الخصائص]  [قاعدة البيانات]                      │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  PROPERTIES TAB:                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  اسم النموذج: [________________]                         │    │
│  │  الوصف: [_______________________________]                │    │
│  │  ملاحظات: [_______________________________]              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  DATABASE TAB:                                                   │
│  ┌─────────────────────┐  ┌─────────────────────────────┐       │
│  │  Available Columns  │  │  Template Structure         │       │
│  │                     │  │                             │       │
│  │  [+ يدوي] [نموذج]   │  │  ┌─────────────────────┐    │       │
│  │  [Excel Upload]     │  │  │ 1. نوع النشاط 🔒    │    │       │
│  │                     │  │  └─────────────────────┘    │       │
│  │  Drag columns ──────┼──┼─▶┌─────────────────────┐    │       │
│  │  to structure       │  │  │ 2. تاريخ التنفيذ    │    │       │
│  │                     │  │  └─────────────────────┘    │       │
│  │  📊 Column 1        │  │  ┌─────────────────────┐    │       │
│  │  📊 Column 2        │  │  │ 3. الملاحظات       │    │       │
│  │  📊 Column 3        │  │  └─────────────────────┘    │       │
│  └─────────────────────┘  └─────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**API Calls**:
- `GET /activities/columns/` - Get available columns
- `GET /activities/templates/:id/` - Get template (edit mode)
- `POST /activities/templates/` - Create template
- `PATCH /activities/templates/:id/` - Update template
- `PUT /activities/templates/:id/columns/` - Update columns
- `POST /activities/columns/detect-from-excel/` - Detect columns from Excel

#### 6. TemplateActivitiesDetail.vue (`/control/templates/:id/activities`) - Admin Only
**Purpose**: Admin view of all submitted activities for a template, grouped by users.

```
┌─────────────────────────────────────────────────────────────────┐
│               TemplateActivitiesDetail.vue (Admin)               │
├─────────────────────────────────────────────────────────────────┤
│  [← رجوع]  Template Name                    [Export All Excel]  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  TABS:  [المستخدمين]  [الأنشطة]                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  USERS TAB:                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐     │
│  │  User Card     │  │  User Card     │  │  User Card     │     │
│  │  ───────────── │  │  ───────────── │  │  ───────────── │     │
│  │  👤 Ahmed      │  │  👤 Mohamed    │  │  👤 Sara       │     │
│  │  Activities: 5 │  │  Activities: 3 │  │  Activities: 8 │     │
│  │  Submitted: 5  │  │  Submitted: 2  │  │  Submitted: 7  │     │
│  └────────────────┘  └────────────────┘  └────────────────┘     │
│                                                                  │
│  Click User → Shows Table of User's Activities                   │
│                                                                  │
│  ACTIVITIES TAB:                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Filters: [User ▼] [Status ▼] [Search...]               │    │
│  │  ┌─────┬─────────┬───────────┬─────────┬────────┐       │    │
│  │  │ #   │ النشاط  │ المستخدم  │ التاريخ │ الحالة │       │    │
│  │  ├─────┼─────────┼───────────┼─────────┼────────┤       │    │
│  │  │  1  │ نشاط 1  │ Ahmed     │ 2024-01 │ مقدم   │       │    │
│  │  │  2  │ نشاط 2  │ Mohamed   │ 2024-02 │ مقدم   │       │    │
│  │  └─────┴─────────┴───────────┴─────────┴────────┘       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**API Calls**:
- `GET /activities/admin/templates/:id/users/` - Get users with submission counts
- `GET /activities/admin/templates/:id/activities/` - Get all activities
- `GET /activities/admin/templates/:id/activities/export/` - Export to Excel

---

## API Endpoints

### Column Definitions (Admin)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/activities/columns/` | List all columns |
| POST | `/activities/columns/` | Create column |
| PATCH | `/activities/columns/:id/` | Update column |
| DELETE | `/activities/columns/:id/` | Soft-delete column |

### Templates (Admin)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/activities/templates/` | List templates |
| POST | `/activities/templates/` | Create template |
| GET | `/activities/templates/:id/` | Get template detail |
| PATCH | `/activities/templates/:id/` | Update template |
| DELETE | `/activities/templates/:id/` | Archive template |
| POST | `/activities/templates/:id/publish/` | Publish template |
| PUT | `/activities/templates/:id/columns/` | Set template columns |

### User Activities
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/activities/titles/` | List published templates |
| GET | `/activities/user/activity-page/` | Get active title page data |
| GET | `/activities/user/templates/:id/activities/` | List user's activities |
| POST | `/activities/user/templates/:id/activities/` | Create activity |
| GET | `/activities/user/activities/:id/` | Get activity detail |
| PATCH | `/activities/user/activities/:id/` | Update activity |
| DELETE | `/activities/user/activities/:id/` | Delete activity |
| POST | `/activities/user/activities/:id/submit/` | Submit activity |

### Admin Views
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/activities/admin/templates/:id/users/` | Users with counts |
| GET | `/activities/admin/templates/:id/activities/` | All activities |
| GET | `/activities/admin/templates/:id/activities/export/` | Export Excel |

### Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/activities/dashboard/summary/` | KPI summary |
| GET | `/activities/dashboard/programs/` | Programs list |
| GET | `/activities/dashboard/programs/:id/` | Program detail |
| GET | `/activities/dashboard/departments/:id/` | Department detail |
| GET | `/activities/dashboard/full/` | Full dashboard data |

---

## User Workflows

### 1. Admin: Create and Publish Template

```
┌─────────────────────────────────────────────────────────────────┐
│                ADMIN: CREATE & PUBLISH TEMPLATE                  │
└─────────────────────────────────────────────────────────────────┘

  1. Navigate to /control/templates
                    │
                    ▼
  2. Click [+ إنشاء قالب جديد]
                    │
                    ▼
  3. Fill Properties (name, description, notes)
                    │
                    ▼
  4. Switch to Database Tab
                    │
                    ▼
  5. Add Columns:
     • Manual: Click [+ يدوي] → Enter name, type, options
     • Excel:  Click [Excel] → Upload file → Auto-detect columns
     • Template: Copy from existing template
                    │
                    ▼
  6. Drag columns to Template Structure
     • Reorder by dragging
     • Set required/optional
     • Remove unwanted columns
                    │
                    ▼
  7. Click [إنشاء] → Template saved as DRAFT
                    │
                    ▼
  8. From TemplateManagement, click [📤 Publish]
                    │
                    ▼
  9. Click [⭐] to set as Active Title
                    │
                    ▼
  ✅ Users can now create activities under this template
```

### 2. User: Create and Submit Activities

```
┌─────────────────────────────────────────────────────────────────┐
│                 USER: CREATE & SUBMIT ACTIVITIES                 │
└─────────────────────────────────────────────────────────────────┘

  1. Navigate to /activities/local (قائمة الأنشطة)
                    │
                    ▼
  2. Active template is auto-selected (or choose from dropdown)
                    │
                    ▼
  3. View existing sheets or create new sheet
                    │
                    ▼
  4. Click [+ إضافة نشاط جديد] or navigate to
     /activities/local/:templateId/create
                    │
                    ▼
  5. Fill in activity form:
     • All template columns displayed as form fields
     • Required fields marked with *
     • Attach files if column allows
                    │
                    ▼
  6. Click [حفظ] → Activity saved as DRAFT
                    │
                    ▼
  7. Repeat steps 4-6 for more activities
                    │
                    ▼
  8. From activity card or detail page, click [تقديم]
     OR submit entire sheet at once
                    │
                    ▼
  ✅ Activity marked as SUBMITTED (read-only)
     Admin can now view in TemplateActivitiesDetail
```

### 3. Admin: Review Submitted Activities

```
┌─────────────────────────────────────────────────────────────────┐
│               ADMIN: REVIEW SUBMITTED ACTIVITIES                 │
└─────────────────────────────────────────────────────────────────┘

  1. Navigate to /control/templates
                    │
                    ▼
  2. Click on a published template card
     → Navigates to /control/templates/:id/activities
                    │
                    ▼
  3. Users Tab (default):
     • See all users who submitted activities
     • Click user card → View their activities in table
                    │
                    ▼
  4. Activities Tab:
     • Filter by user, status, search
     • Click activity → Side panel preview
     • View full details
                    │
                    ▼
  5. Export:
     • Click [Export Excel] → Download all activities
     • Includes all columns, users, submission dates
                    │
                    ▼
  ✅ Admin has full visibility into all submitted data
```

---

## Service Layer (Frontend)

The frontend uses `activityService.ts` which provides:

```typescript
// Column Management (Admin)
columnService.getAll()
columnService.create()
columnService.update()
columnService.delete()

// Template Management (Admin)
templateService.getAll()
templateService.create()
templateService.update()
templateService.publish()
templateService.setColumns()

// User Activities
titleService.getPublishedTitles()
userActivitiesService.getActivities()
userActivitiesService.createActivity()
userActivitiesService.updateActivity()
userActivitiesService.deleteActivity()
userActivitiesService.submitActivity()

// Admin Views
titleService.getAdminTemplateActivities()
titleService.getAdminTemplateUsers()
titleService.exportTemplateActivities()

// Dashboard
dashboardService.getFullDashboard()
dashboardService.getProgramDetail()
dashboardService.getDepartmentDetail()
```

---

## Key Concepts

### Column Definition vs Template Column
- **Column Definition**: Global column type created by admin (e.g., "نوع النشاط" as text field)
- **Template Column**: Configuration of a column within a specific template (order, width, required)

### Sheet vs Activity (Row)
- **Sheet**: Container for user's activities under a template (like a workbook)
- **Activity (Row)**: Individual activity entry with data for all columns

### Template Status
- **Draft**: Being edited, columns can change, users cannot create activities
- **Published**: Live, columns frozen, users can create activities
- **Archived**: Soft-deleted, existing sheets remain accessible

### Active Title
- A published template can be marked as "Active Title"
- Multiple templates can be active simultaneously
- Active templates appear in the user's template dropdown

---

## File Structure

```
activities/
├── models.py           # Database models
├── views.py            # API endpoints (3600+ lines)
├── serializers.py      # DRF serializers
├── urls.py             # URL routing
├── permissions.py      # Permission classes
├── pagination.py       # Cursor pagination
├── validators.py       # Validation logic
├── constants.py        # System column keys
├── dashboard_utils.py  # Dashboard calculations
├── excel_service.py    # Excel import/export
├── signals.py          # Django signals
└── migrations/         # Database migrations
```
