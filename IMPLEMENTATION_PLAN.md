Implement the following plan:

# Symptom Logging: Per-Symptom Times & Ongoing Detection Refinements

## Overview
Refine symptom logging with per-symptom start/end times, immediate ongoing symptom detection, and improved severity scale (0-10 instead of 1-10).

## Requirements Summary

### 1. Severity Scale Refinement
**Current:** 1 <= mild < 4 <= moderate < 7 <= severe <= 10
**New:** 1 <= mild < 4 <= moderate < 7 <= severe <= 10

Changes:
- Slider range: `min="1"` (unchanged)
- Default severity: 4.0 (moderate middle, was 5.0)
- Thresholds: mild (1-3.99), moderate (4-6.99), severe (7-10)

### 2. Per-Symptom Start/End Times
**Current:** Global start/end time for all symptoms
**New:** Each symptom has optional individual times + global "Apply to all"

Features:
- Checkboxes per symptom: "Set start time", "Set end time"
- When checked, show datetime-local input
- Global time inputs at top with "Apply to all symptoms" button
- Individual times override global settings
- On submit, send per-symptom times in tags JSON

### 3. Ongoing Symptom Detection
**Current:** Episode detection checks all tags together, shows confirmation at form level
**New:** Immediate per-symptom detection when tag is added

Features:
- **Trigger:** Check immediately when each symptom is added (in `addTag()`)
- **Lookback window:** 3 days (72 hours, increased from 48h)
- **Detection logic:** Search for similar symptom by name (not all tags)
- **Popup UI:**
  - Title: "Possible ongoing symptom detected"
  - Shows: Original symptom name, date logged, severity
  - If symptom names differ:
    - Show 3 options: "Use original name", "Use new name", "Ignore"
    - System recommends best match (bias toward existing tags)
  - If names match or user selects original/new:
    - Show what will be inherited: "Will inherit start time from [date]"
- **On confirm:**
  - Link to original symptom via `episode_id`
  - Auto-set start time to original symptom's start time
  - Keep end time blank (ongoing)
  - Auto-populate symptom name if user chose "Use original name"

---

## Current Implementation Analysis

### Existing Episode Detection (to be adapted)

**API Endpoint:** `POST /symptoms/detect-episode`
- Location: `app/api/symptoms.py:233-299`
- Accepts: `tags` (list), `start_time`
- Returns: `potential_episode`, `is_continuation`, `confidence`, `reasoning`
- Called: On form load, tag add/remove, start time change

**Service Method:** `detect_similar_recent_symptoms()`
- Location: `app/services/symptom_service.py:284-336`
- Current behavior: Searches for ANY matching tag in 48-hour window
- Uses PostgreSQL JSONB matching: `LOWER(tag->>'name') = ANY(:tag_names)`
- Returns most recent match

**AI Analysis:** `detect_episode_continuation()`
- Location: `app/services/ai_service.py:476-561`
- Analyzes: tag overlap, temporal continuity, severity pattern, semantic similarity
- Confidence thresholds: <0.3 unlikely, 0.4-0.6 possible, 0.7-0.9 likely, >0.9 very likely

**Frontend:** `checkForEpisode()`
- Location: `app/templates/symptoms/log.html:84-113`
- Shows yellow warning box with radio buttons (yes/no)
- Only displays if `confidence > 0.5`

---

## Implementation Plan

### Phase 1: Backend - Per-Symptom Ongoing Detection

#### 1.1 New API Endpoint for Per-Symptom Detection

**File:** `app/api/symptoms.py`

**Add new Pydantic model:**
```python
class DetectOngoingSymptomRequest(BaseModel):
    symptom_name: str
    symptom_severity: int
    current_time: Optional[str] = None  # ISO format, defaults to now
```

**Add new endpoint:**
```python
@router.post("/detect-ongoing")
async def detect_ongoing_symptom(
    request: DetectOngoingSymptomRequest,
    db: Session = Depends(get_db)
):
    """
    Detect if a single symptom is ongoing from recent history (3-day window).

    Returns:
        {
            "potential_ongoing": {...} or null,
            "is_ongoing": bool,
            "confidence": float,
            "reasoning": str,
            "name_match": "exact" | "similar" | "different",
            "recommended_name": str  # If names differ, what system recommends
        }
    """
    try:
        current_time = datetime.fromisoformat(request.current_time) if request.current_time else datetime.utcnow()

        # Search for similar symptom by name (3-day window)
        previous_symptom = symptom_service.detect_ongoing_symptom_by_name(
            db=db,
            user_id=MVP_USER_ID,
            symptom_name=request.symptom_name,
            lookback_hours=72  # 3 days
        )

        if not previous_symptom:
            return {
                "potential_ongoing": None,
                "is_ongoing": False,
                "confidence": 0.0,
                "reasoning": "No similar symptom found in the past 3 days"
            }

        # AI analysis for nuanced determination
        previous_data = {
            "name": previous_symptom.tags[0]["name"] if previous_symptom.tags else request.symptom_name,
            "severity": previous_symptom.tags[0]["severity"] if previous_symptom.tags else 0,
            "start_time": previous_symptom.start_time or previous_symptom.timestamp,
            "end_time": previous_symptom.end_time
        }

        current_data = {
            "name": request.symptom_name,
            "severity": request.symptom_severity,
            "time": current_time
        }

        ai_result = await claude_service.detect_ongoing_symptom(
            previous_symptom=previous_data,
            current_symptom=current_data
        )

        # Determine name match type
        prev_name = previous_data["name"].lower()
        curr_name = request.symptom_name.lower()

        if prev_name == curr_name:
            name_match = "exact"
            recommended_name = prev_name
        else:
            name_match = "different"
            # Bias toward existing tag (previous symptom)
            recommended_name = previous_data["name"]

        return {
            "potential_ongoing": {
                "id": previous_symptom.id,
                "name": previous_data["name"],
                "severity": previous_data["severity"],
                "start_time": previous_symptom.start_time.isoformat() if previous_symptom.start_time else previous_symptom.timestamp.isoformat(),
                "end_time": previous_symptom.end_time.isoformat() if previous_symptom.end_time else None
            },
            "is_ongoing": ai_result["is_ongoing"],
            "confidence": ai_result["confidence"],
            "reasoning": ai_result["reasoning"],
            "name_match": name_match,
            "recommended_name": recommended_name
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ongoing detection failed: {str(e)}")
```

#### 1.2 Update Symptom Service

**File:** `app/services/symptom_service.py`

**Add new method:**
```python
@staticmethod
def detect_ongoing_symptom_by_name(
    db: Session,
    user_id: UUID,
    symptom_name: str,
    lookback_hours: int = 72
) -> Optional[Symptom]:
    """
    Find most recent symptom matching a specific name within lookback window.

    Args:
        db: Database session
        user_id: User ID
        symptom_name: Symptom name to search for
        lookback_hours: How far back to search (default 72h = 3 days)

    Returns:
        Most recent matching Symptom or None
    """
    cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)

    # Search for symptom with matching tag name
    symptom = db.query(Symptom).filter(
        Symptom.user_id == user_id,
        Symptom.tags.isnot(None),
        or_(
            Symptom.start_time >= cutoff_time,
            Symptom.timestamp >= cutoff_time
        ),
        # Check if any tag matches the symptom name (case-insensitive)
        func.lower(Symptom.tags.op('->>')(0)['name'].astext) == symptom_name.lower()
    ).order_by(
        func.coalesce(Symptom.start_time, Symptom.timestamp).desc()
    ).first()

    return symptom
```

**Note:** Current implementation uses `tag->>'name'` for JSONB tag extraction. May need to adjust based on actual tag structure in database.

#### 1.3 Update AI Service

**File:** `app/services/ai_service.py`

**Add new method:**
```python
async def detect_ongoing_symptom(
    self,
    previous_symptom: dict,
    current_symptom: dict
) -> dict:
    """
    Determine if current symptom is ongoing from previous occurrence.

    Args:
        previous_symptom: {name, severity, start_time, end_time}
        current_symptom: {name, severity, time}

    Returns:
        {
            "is_ongoing": bool,
            "confidence": float (0-1),
            "reasoning": str
        }
    """
    try:
        # Build analysis context
        analysis_data = {
            "previous_symptom": {
                "name": previous_symptom.get("name"),
                "severity": previous_symptom.get("severity"),
                "start_time": previous_symptom.get("start_time").isoformat() if isinstance(previous_symptom.get("start_time"), datetime) else previous_symptom.get("start_time"),
                "end_time": previous_symptom.get("end_time").isoformat() if previous_symptom.get("end_time") else None
            },
            "current_symptom": {
                "name": current_symptom.get("name"),
                "severity": current_symptom.get("severity"),
                "time": current_symptom.get("time").isoformat() if isinstance(current_symptom.get("time"), datetime) else current_symptom.get("time")
            }
        }

        # Call Claude with same prompt as episode detection
        response = self.client.messages.create(
            model=self.sonnet_model,
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": f"Analyze if this symptom is ongoing:\n\n{json.dumps(analysis_data, indent=2)}"
                }
            ],
            system=EPISODE_CONTINUATION_SYSTEM_PROMPT  # Reuse existing prompt
        )

        raw_response = response.content[0].text

        # Parse JSON response
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            if "```json" in raw_response:
                json_str = raw_response.split("```json")[1].split("```")[0].strip()
                parsed = json.loads(json_str)
            elif "```" in raw_response:
                json_str = raw_response.split("```")[1].split("```")[0].strip()
                parsed = json.loads(json_str)
            else:
                raise ValueError("Could not parse AI response as JSON")

        return {
            "is_ongoing": parsed.get("is_continuation", False),  # Reuse continuation logic
            "confidence": parsed.get("confidence", 0.0),
            "reasoning": parsed.get("reasoning", "")
        }

    except Exception as e:
        raise ValueError(f"AI ongoing detection failed: {str(e)}")
```

---

### Phase 2: Frontend - Per-Symptom Times UI

#### 2.1 Update Alpine.js State

**File:** `app/templates/symptoms/log.html`

**Modify `x-data` to include:**
```javascript
x-data="{
    selectedTags: [],  // Now: [{name, severity, expanded, startTime, endTime, showStartTime, showEndTime, episodeId}, ...]
    currentTag: '',
    autocompleteSuggestions: [],
    commonTags: [],
    globalStartTime: new Date().toISOString().slice(0, 16),
    globalEndTime: '',
    showGlobalEndTime: false,
    aiGeneratedText: null,
    finalNotes: null,
    isGeneratingAi: false,
    ongoingDetection: null,      // NEW: Holds ongoing detection result for popup
    showOngoingPopup: false,      // NEW: Controls popup visibility
    pendingTagIndex: null,        // NEW: Index of tag being processed for ongoing
    isSubmitting: false,

    // ... methods
}"
```

**Each tag object structure:**
```javascript
{
    name: string,
    severity: number (0-10),
    expanded: boolean,
    startTime: string | null,       // NEW: ISO datetime or null
    endTime: string | null,         // NEW: ISO datetime or null
    showStartTime: boolean,         // NEW: Checkbox state
    showEndTime: boolean,           // NEW: Checkbox state
    episodeId: number | null        // NEW: Link to original symptom if ongoing
}
```

#### 2.2 Update `addTag()` Method with Ongoing Detection

```javascript
async addTag(name, severity = 4.0) {  // Changed default from 5.0 to 4.0
    // Don't add duplicates
    if (this.selectedTags.some(t => t.name.toLowerCase() === name.toLowerCase())) {
        return;
    }

    // Add new tag at START (unshift), expanded
    const newTag = {
        name: name,
        severity: severity,
        expanded: true,
        startTime: null,
        endTime: null,
        showStartTime: false,
        showEndTime: false,
        episodeId: null
    };

    this.selectedTags.unshift(newTag);

    // Collapse all other tags
    for (let i = 1; i < this.selectedTags.length; i++) {
        this.selectedTags[i].expanded = false;
    }

    this.currentTag = '';
    this.autocompleteSuggestions = [];

    // Check for ongoing symptom (NEW)
    await this.checkForOngoing(0);  // Index 0 = just-added tag
}
```

#### 2.3 Add `checkForOngoing()` Method

```javascript
async checkForOngoing(tagIndex) {
    const tag = this.selectedTags[tagIndex];

    try {
        const response = await fetch('/symptoms/detect-ongoing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symptom_name: tag.name,
                symptom_severity: Math.round(tag.severity),
                current_time: new Date().toISOString()
            })
        });

        const data = await response.json();

        if (data.potential_ongoing && data.confidence > 0.5) {
            this.ongoingDetection = data;
            this.pendingTagIndex = tagIndex;
            this.showOngoingPopup = true;
        }
    } catch (error) {
        console.error('Ongoing detection failed:', error);
    }
}
```

#### 2.4 Add Ongoing Popup Handlers

```javascript
confirmOngoing(choice) {
    const tagIndex = this.pendingTagIndex;
    const tag = this.selectedTags[tagIndex];
    const detection = this.ongoingDetection;

    if (choice === 'ignore') {
        // User chose not to link
        this.closeOngoingPopup();
        return;
    }

    // Link to episode
    tag.episodeId = detection.potential_ongoing.id;

    // Inherit start time from original symptom
    tag.startTime = detection.potential_ongoing.start_time.slice(0, 16);  // Format for datetime-local
    tag.showStartTime = true;

    // Handle name choice
    if (choice === 'use_original') {
        tag.name = detection.recommended_name;
    } else if (choice === 'use_new') {
        // Keep current name
    }

    this.closeOngoingPopup();
},

closeOngoingPopup() {
    this.showOngoingPopup = false;
    this.ongoingDetection = null;
    this.pendingTagIndex = null;
}
```

#### 2.5 Add Global Time Controls UI

**Location:** Before symptom tag input section

```html
<!-- Global Time Controls -->
<div style="background: var(--card-background-color); padding: 1rem; border-radius: var(--border-radius); margin-bottom: 1.5rem;">
    <label style="font-weight: bold; margin-bottom: 0.5rem; display: block;">
        Global Time Settings (Optional)
        <small>Apply default times to all symptoms</small>
    </label>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
        <div>
            <label for="global-start-time">Default Start Time</label>
            <input
                type="datetime-local"
                id="global-start-time"
                x-model="globalStartTime"
                style="margin-bottom: 0;"
            >
        </div>

        <div>
            <label>
                <input type="checkbox" x-model="showGlobalEndTime">
                Set default end time
            </label>
            <div x-show="showGlobalEndTime" x-cloak>
                <input
                    type="datetime-local"
                    x-model="globalEndTime"
                >
            </div>
        </div>
    </div>

    <button
        type="button"
        class="outline"
        @click="applyTimesToAll()"
        :disabled="selectedTags.length === 0"
    >
        Apply to All Symptoms
    </button>
</div>
```

#### 2.6 Add `applyTimesToAll()` Method

```javascript
applyTimesToAll() {
    for (let tag of this.selectedTags) {
        tag.startTime = this.globalStartTime;
        tag.showStartTime = true;

        if (this.showGlobalEndTime && this.globalEndTime) {
            tag.endTime = this.globalEndTime;
            tag.showEndTime = true;
        }
    }
}
```

#### 2.7 Update Symptom Card Expanded View

**Add time controls to expanded symptom card:**

```html
<!-- Expanded view (conditional) -->
<div x-show="tag.expanded" x-cloak style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--muted-border-color);">
    <!-- Severity slider (existing code) -->
    <!-- ... -->

    <!-- Per-Symptom Time Controls (NEW) -->
    <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--muted-border-color);">
        <div style="margin-bottom: 0.5rem;">
            <label>
                <input type="checkbox" x-model="tag.showStartTime" @click.stop>
                Set start time
            </label>
        </div>

        <div x-show="tag.showStartTime" x-cloak style="margin-bottom: 1rem;">
            <input
                type="datetime-local"
                x-model="tag.startTime"
                @click.stop
                style="width: 100%;"
            >
        </div>

        <div style="margin-bottom: 0.5rem;">
            <label>
                <input type="checkbox" x-model="tag.showEndTime" @click.stop>
                Set end time
            </label>
        </div>

        <div x-show="tag.showEndTime" x-cloak>
            <input
                type="datetime-local"
                x-model="tag.endTime"
                @click.stop
                style="width: 100%;"
            >
        </div>
    </div>

    <!-- Remove button (existing) -->
    <!-- ... -->
</div>
```

#### 2.8 Add Ongoing Detection Popup UI

**Location:** After episode detection UI, before submit buttons

```html
<!-- Ongoing Symptom Detection Popup -->
<div x-show="showOngoingPopup && ongoingDetection" x-cloak style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 9999; display: flex; align-items: center; justify-content: center;">
    <div style="background: white; padding: 2rem; border-radius: var(--border-radius); max-width: 500px; width: 90%;">
        <h3 style="margin-top: 0;">⚠️ Possible Ongoing Symptom Detected</h3>

        <p>
            You previously logged
            <strong x-text="ongoingDetection?.potential_ongoing?.name"></strong>
            (severity: <span x-text="ongoingDetection?.potential_ongoing?.severity"></span>/10)
            on <strong x-text="ongoingDetection?.potential_ongoing?.start_time ? new Date(ongoingDetection.potential_ongoing.start_time).toLocaleString() : ''"></strong>.
        </p>

        <div x-show="ongoingDetection && ongoingDetection.confidence > 0.7" style="font-size: 0.9rem; color: var(--muted-color); margin-bottom: 1rem; font-style: italic;">
            <span x-text="ongoingDetection?.reasoning"></span>
        </div>

        <!-- Name Match Options (show if names differ) -->
        <div x-show="ongoingDetection && ongoingDetection.name_match === 'different'" style="margin-bottom: 1.5rem; padding: 1rem; background: #f0f0f0; border-radius: var(--border-radius);">
            <p style="margin-top: 0;"><strong>Symptom names differ. Choose one:</strong></p>
            <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                <button type="button" class="outline" @click="confirmOngoing('use_original')" style="text-align: left;">
                    Use original name: <strong x-text="ongoingDetection?.recommended_name"></strong> (Recommended)
                </button>
                <button type="button" class="outline" @click="confirmOngoing('use_new')" style="text-align: left;">
                    Use new name: <strong x-text="selectedTags[pendingTagIndex]?.name"></strong>
                </button>
            </div>
        </div>

        <!-- Inheritance Info -->
        <div style="background: #e3f2fd; padding: 1rem; border-radius: var(--border-radius); margin-bottom: 1.5rem;">
            <p style="margin: 0;"><strong>If you link this as ongoing:</strong></p>
            <ul style="margin: 0.5rem 0 0 0; padding-left: 1.5rem;">
                <li>Start time will be inherited from <span x-text="ongoingDetection?.potential_ongoing?.start_time ? new Date(ongoingDetection.potential_ongoing.start_time).toLocaleString() : ''"></span></li>
                <li>This will be linked to the previous symptom episode</li>
            </ul>
        </div>

        <!-- Action Buttons -->
        <div style="display: flex; gap: 1rem;">
            <button type="button" @click="confirmOngoing('use_original')" x-show="ongoingDetection && ongoingDetection.name_match === 'exact'">
                Yes, Link as Ongoing
            </button>
            <button type="button" class="secondary" @click="confirmOngoing('ignore')">
                No, This is New
            </button>
        </div>
    </div>
</div>
```

#### 2.9 Update `submitForm()` to Send Per-Symptom Times

```javascript
async submitForm() {
    if (this.selectedTags.length === 0) {
        alert('Please add at least one symptom tag');
        return;
    }

    this.isSubmitting = true;

    // Build form data
    const formData = new FormData();

    // Build tags with per-symptom times
    const tagsToSubmit = this.selectedTags.map(tag => ({
        name: tag.name,
        severity: Math.round(tag.severity),
        start_time: tag.showStartTime && tag.startTime ? new Date(tag.startTime).toISOString() : null,
        end_time: tag.showEndTime && tag.endTime ? new Date(tag.endTime).toISOString() : null,
        episode_id: tag.episodeId || null
    }));

    formData.append('tags_json', JSON.stringify(tagsToSubmit));

    // Send AI text fields
    formData.append('ai_generated_text', this.aiGeneratedText || '');
    formData.append('final_notes', this.finalNotes || '');

    // Submit form
    try {
        const response = await fetch('/symptoms/create-tagged', {
            method: 'POST',
            body: formData
        });

        if (response.redirected) {
            window.location.href = response.url;
        } else if (response.ok) {
            window.location.href = '/symptoms/history?success=true';
        } else {
            const error = await response.text();
            alert('Failed to save symptom: ' + error);
            this.isSubmitting = false;
        }
    } catch (error) {
        console.error('Submit failed:', error);
        alert('Failed to save symptom: ' + error);
        this.isSubmitting = false;
    }
}
```

---

### Phase 3: Backend - Handle Per-Symptom Data on Creation

#### 3.1 Update Tag Schema Validation

**File:** `app/services/symptom_service.py`

**Update `create_symptom_with_tags()` method:**

```python
@staticmethod
def create_symptom_with_tags(
    db: Session,
    user_id: UUID,
    tags: List[Dict],
    ai_generated_text: Optional[str] = None,
    final_notes: Optional[str] = None
) -> Symptom:
    """
    Create symptom with tag-based schema (now supports per-symptom times).

    Args:
        db: Database session
        user_id: User ID
        tags: List of {"name": str, "severity": int, "start_time": str?, "end_time": str?, "episode_id": int?}
        ai_generated_text: Original AI response (nullable)
        final_notes: User-edited text (nullable)

    Returns:
        Created Symptom object
    """
    # Validate tags format
    if not tags:
        raise ValueError("At least one tag is required")

    for tag in tags:
        if "name" not in tag or "severity" not in tag:
            raise ValueError("Each tag must have 'name' and 'severity' fields")
        if not isinstance(tag["severity"], int) or not 1 <= tag["severity"] <= 10:
            raise ValueError("Severity must be an integer between 1 and 10")

    # Determine global start/end from first tag with times set
    global_start_time = None
    global_end_time = None
    episode_id = None

    for tag in tags:
        if tag.get("start_time") and not global_start_time:
            global_start_time = datetime.fromisoformat(tag["start_time"])
        if tag.get("end_time") and not global_end_time:
            global_end_time = datetime.fromisoformat(tag["end_time"])
        if tag.get("episode_id") and not episode_id:
            episode_id = tag["episode_id"]

    # Fallback to current time if no times specified
    if not global_start_time:
        global_start_time = datetime.utcnow()

    # Populate backward-compatible fields
    sorted_tags = sorted(tags, key=lambda t: t["severity"], reverse=True)
    most_severe_tag = sorted_tags[0]

    structured_type = most_severe_tag["name"].lower()
    severity = most_severe_tag["severity"]

    # Generate description from tags if final_notes is empty
    if not final_notes and tags:
        tag_descriptions = [f"{t['name']} ({t['severity']}/10)" for t in tags]
        raw_description = ", ".join(tag_descriptions)
    else:
        raw_description = final_notes or ""

    # Set deprecated fields for backward compatibility
    ai_elaborated = ai_generated_text is not None
    user_edited = (ai_generated_text is not None and
                  final_notes is not None and
                  ai_generated_text != final_notes)

    symptom = Symptom(
        user_id=user_id,
        raw_description=raw_description,
        structured_type=structured_type,
        severity=severity,
        notes=final_notes,
        tags=tags,  # Store with per-symptom times
        start_time=global_start_time,
        end_time=global_end_time,
        episode_id=episode_id,
        # New fields
        ai_generated_text=ai_generated_text,
        final_notes=final_notes,
        # Deprecated fields
        ai_elaborated=ai_elaborated,
        ai_elaboration_response=ai_generated_text,
        user_edited_elaboration=user_edited,
        timestamp=global_start_time
    )

    db.add(symptom)
    db.commit()
    db.refresh(symptom)
    return symptom
```

**Note:** Tags JSON now includes `start_time`, `end_time`, `episode_id` per tag. Global symptom `start_time`/`end_time` use first tag's times as fallback.

---

### Phase 4: Update Severity Scale

#### 4.1 Update Frontend Severity Functions

**File:** `app/templates/symptoms/log.html`

```javascript
getSeverityColor(severity) {
    if (severity < 4) return 'var(--form-element-valid-border-color)';  // Changed: < 4 (was <= 3)
    if (severity < 7) return '#f5a623';                                  // Changed: < 7 (was <= 6)
    return 'var(--form-element-invalid-border-color)';
},

getSeverityLabel(severity) {
    if (severity < 4) return 'mild';      // Changed: < 4 (was <= 3)
    if (severity < 7) return 'moderate';  // Changed: < 7 (was <= 6)
    return 'severe';
}
```

#### 4.2 Update Slider Attributes

**Change all severity sliders:**

```html
<input
    type="range"
    min="1"
    max="10"
    step="0.1"
    x-model.number="tag.severity"
    :style="{ accentColor: getSeverityColor(tag.severity) }"
>
<div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: var(--muted-color); margin-top: 0.25rem;">
    <span>mild (1)</span>
    <span>moderate (5)</span>
    <span>severe (10)</span>
</div>
```

---

## Testing & Verification

### Test Cases

#### 1. Severity Scale (1-10)
- [ ] Slider allows values 1-10 (unchanged)
- [ ] Default severity is 4.0 (moderate)
- [ ] Labels: 1-3.99 = mild, 4-6.99 = moderate, 7-10 = severe
- [ ] Colors change at correct thresholds
- [ ] Collapsed view shows correct label

#### 2. Per-Symptom Times
- [ ] Global time inputs work
- [ ] "Apply to all symptoms" button sets all times
- [ ] Per-symptom checkboxes appear in expanded card
- [ ] Checking "Set start time" shows datetime input
- [ ] Individual times override global times
- [ ] Submitted tags JSON includes per-symptom times

#### 3. Ongoing Detection
- [ ] Popup appears immediately when adding symptom
- [ ] Shows previous symptom name, date, severity
- [ ] If names differ, shows 3 options with recommendation
- [ ] "Use original name" updates tag name
- [ ] "Link as ongoing" inherits start time
- [ ] Episode ID is set correctly
- [ ] "No, this is new" closes popup without linking
- [ ] Detection uses 3-day (72h) window

#### 4. Database Verification
```sql
-- Verify tags include per-symptom times
SELECT id, tags::text FROM symptoms ORDER BY id DESC LIMIT 1;

-- Expected format:
-- [{"name": "bloating", "severity": 7, "start_time": "2026-01-30T10:00:00", "episode_id": 2}]

-- Verify episode linking
SELECT id, episode_id, start_time FROM symptoms WHERE episode_id IS NOT NULL;
```

---

## Critical Files to Modify

1. **`app/api/symptoms.py`**
   - Add `POST /symptoms/detect-ongoing` endpoint
   - Add `DetectOngoingSymptomRequest` model

2. **`app/services/symptom_service.py`**
   - Add `detect_ongoing_symptom_by_name()` method
   - Update `create_symptom_with_tags()` to handle per-symptom times

3. **`app/services/ai_service.py`**
   - Add `detect_ongoing_symptom()` method (reuses episode continuation prompt)

4. **`app/templates/symptoms/log.html`**
   - Update Alpine state: add time properties to tags
   - Add `checkForOngoing()` method
   - Add `confirmOngoing()` / `closeOngoingPopup()` methods
   - Add `applyTimesToAll()` method
   - Update `addTag()` to trigger ongoing detection
   - Update `submitForm()` to send per-symptom times
   - Update severity functions (0-10 scale)
   - Add global time controls UI
   - Add per-symptom time checkboxes in expanded card
   - Add ongoing detection popup UI

---

## Implementation Sequence

1. **Backend API** (1-2 hours)
   - Add `/symptoms/detect-ongoing` endpoint
   - Add `detect_ongoing_symptom_by_name()` service method
   - Add `detect_ongoing_symptom()` AI method
   - Test with curl

2. **Frontend State & Detection** (2-3 hours)
   - Update Alpine state with time properties
   - Add `checkForOngoing()` method
   - Add ongoing popup handlers
   - Update `addTag()` to call detection
   - Test detection flow

3. **Per-Symptom Time UI** (1-2 hours)
   - Add global time controls
   - Add per-symptom time checkboxes
   - Add `applyTimesToAll()` method
   - Update submit logic

4. **Severity Scale Update** (15 min)
   - Update severity threshold functions (1-3.99 = mild, etc.)
   - Update default severity to 4.0

5. **Integration Testing** (1 hour)
   - End-to-end symptom logging
   - Ongoing detection flow
   - Database verification
   - Cross-browser testing

**Total Estimated Time:** 6-8 hours

---

## Debugging History Page Display Issue

### Problem
Symptoms exist in database (verified via SQL query) but not rendering in `/symptoms/history` template. Database shows 5 symptoms with proper JSONB tags structure:
```
id=5: tags=[{"name": "bloating", "severity": 6, ...}, {"name": "cramping", "severity": 7, ...}]
```

Template already fixed to use dictionary access (`tag['name']`, `tag['severity']`) instead of attribute access, but issue persists.

### Debugging Steps (Keep Simple)

1. **Check if symptoms reach template**
   - Add temporary debug output: `<p>DEBUG: {{ symptoms|length }} symptoms found</p>` near top of history.html
   - If 0: Problem is in API endpoint or service query
   - If > 0: Problem is in template rendering logic

2. **Check JSONB field hydration**
   - Add debug: `<p>DEBUG: First symptom tags = {{ symptoms[0].tags if symptoms else 'none' }}</p>`
   - If None: SQLAlchemy isn't loading JSONB field
   - If shows data: Template conditional logic is wrong

3. **Check template conditional logic**
   - Current condition: `{% if symptom.tags %}`
   - If tags = None (not empty list), condition fails
   - Quick fix: Change to `{% if symptom.tags is not none %}`

4. **Check Jinja2 JSONB iteration**
   - JSONB columns may return as string, not parsed JSON
   - If tags is string, iteration fails silently
   - Fix: Parse in template or ensure SQLAlchemy loads as dict

### Most Likely Issues (In Order)

1. **Template conditional is wrong**: `{% if symptom.tags %}` fails if tags is None or empty list
2. **JSONB not parsed**: SQLAlchemy returns string instead of dict/list
3. **Symptoms not loaded**: API endpoint query failing silently

### Quick Fix Strategy

1. Add debug lines to template
2. Check Playwright output to see what renders
3. Based on debug output, apply targeted fix:
   - If symptoms don't reach template: Check API endpoint
   - If tags is None: Check SQLAlchemy column definition
   - If tags is string: Add JSON parsing in template or model
   - If tags is list but empty: Check database data integrity

### Files to Check/Modify

- `app/templates/symptoms/history.html` - Add debug output, fix conditionals
- `app/api/symptoms.py:508-524` - Verify query returns symptoms
- `app/models/symptom.py:29` - Verify JSONB column loads correctly

### Playwright Verification

After fix:
```javascript
await page.goto('http://localhost:5001/symptoms/history');
await page.screenshot({ path: 'history-debug.png' });
const symptomCards = await page.locator('.symptom-card').count();
console.log(`Found ${symptomCards} symptom cards`);
```

Expected: 5 symptom cards visible


If you need specific details from before exiting plan mode (like exact code snippets, error messages, or content you generated), read the full transcript at: /Users/twm/.claude/projects/-Users-twm-Library-CloudStorage-OneDrive-Personal-Coding-Projects-bloaty-mcbloatface/adc193f6-4c14-4749-b4ae-3cf91aa0999f.jsonl