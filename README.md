# On-Call Schedule Generator

An automated on-call scheduling system using Google OR-Tools CP-SAT solver to generate fair, constraint-based schedules for engineering teams.

## Requirements

- Python 3.7+
- **Google OR-Tools** (`ortools>=9.5`) - Provides the CP-SAT constraint programming solver
- PyYAML (`pyyaml>=6.0`) - For reading YAML configuration files

## Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## File Structure

```
oncall/
├── oncall.py              # CLI interface
├── solver.py              # Core scheduling engine
├── config.yaml            # Your configuration
├── availability.csv       # Unavailability data
├── requirements.txt       # Python dependencies
├── schedule.csv           # Generated schedule (CSV)
└── schedule.ics           # Generated schedule (iCal)
```

## Quick Start

```bash
# Validate your configuration
python oncall.py validate --config config.yaml

# Generate schedule
python oncall.py generate --config config.yaml
```

## How It Works

The scheduler uses **Google OR-Tools CP-SAT solver** (Constraint Programming - Satisfiability) to generate fair on-call schedules. CP-SAT finds optimal solutions to scheduling problems with multiple constraints.

**Algorithm:** `ortools.sat.python.cp_model` (CP-SAT Solver)

The system models your scheduling requirements as constraints and lets the solver find valid assignments that:
- Prevent engineers from working consecutive weeks
- Balance workload across the team
- Respect availability/vacation constraints
- Handle multi-block scheduling
- Optimize for fairness and feasibility

## Configuration

All scheduling is controlled via `config.yaml`:

### Basic Structure

**Note:** The `start_date` can be **any day of the week**. When you specify days in role schedules (e.g., `[Mon, Tue, Wed]`), the system maps them to the actual calendar days, regardless of when your week starts.

<details>
<summary>Example: Starting on Wednesday</summary>

If your schedule starts on Wednesday Nov 5, 2025:
- Week 1 = Nov 5-11 (Wed-Tue)
- A role with `days: [Mon, Tue, Wed]` will schedule shifts on:
  - **Mon Nov 10** (the Monday in that week)
  - **Tue Nov 11** (the Tuesday in that week)  
  - **Wed Nov 5** (the Wednesday in that week)

The day names in the config always refer to actual calendar days, not offsets.
</details>

```yaml
# Team members
team:
  - Alice
  - Bob
  - Charlie
  # ... add all your engineers

# Scheduling parameters
schedule:
  start_date: "2025-11-03"  # Can be any day of the week
  num_blocks: 2              # Number of scheduling blocks
  weeks_per_block: 12        # Weeks per block (configurable)
  timezone: "UTC"

# Role definitions with actual shift times
roles:
  D:
    name: "Day Shift"
    schedule:
      - days: [Mon, Tue, Wed, Thu, Fri]
        start_time: "09:00"
        end_time: "17:00"
  
  NP:
    name: "Night Primary"
    schedule:
      - days: [Mon, Tue, Wed, Thu]  # Weeknights
        start_time: "17:00"
        end_time: "09:00"
      - days: [Fri]  # Weekend shift
        start_time: "17:00"
        end_time: "09:00"
        span_days: 3  # Fri 17:00 → Mon 09:00
  
  NS:
    name: "Night Secondary"
    schedule:
      # Same as NP

# Constraints
constraints:
  max_shifts_per_engineer: 3   # Per block
  max_weekends_per_engineer: 1
  weekend_role: NP             # Which role includes weekends

# Rule toggles (enable/disable constraints)
rules:
  roster_completeness: true    # All roles must be filled
  no_consecutive_weeks: true   # No back-to-back weeks
  max_workload: true           # Enforce max_shifts limit
  weekend_limit: true          # Enforce weekend limit
  role_separation: true        # One role per person per week
  availability: true           # Respect unavailability

# Solver settings
solver:
  timeout_seconds: 60

# Output configuration
files:
  availability_csv: "availability.csv"
  export_formats:
    - csv
    - ical
```

## Specifying Unavailability

Create `availability.csv` with date ranges when engineers are unavailable:

```csv
engineer,start_date,end_date
Diana,2025-11-24,2025-11-30
Bob,2025-12-15,2025-12-30
Alice,2026-02-16,2026-02-22
```

The system maps these to the corresponding weeks in each block.

## CLI Commands

### Validate Configuration

```bash
python oncall.py validate --config config.yaml
```

Checks:
- All required fields are present
- Capacity is sufficient (engineers × max_shifts ≥ weeks × roles)
- Configuration is well-formed

### Generate Schedule

```bash
# Generate with default output
python oncall.py generate --config config.yaml

# Specify output directory
python oncall.py generate --config config.yaml --output-dir schedules/
```

Outputs:
- **Console**: Human-readable schedule table
- **schedule.csv**: Detailed shift list with exact start/end times
- **schedule.ics**: iCalendar file for importing to calendars

### Get Help

```bash
python oncall.py --help
python oncall.py generate --help
```

## Understanding the Output

### Console Output

```
Week   | Dates         | D          | NP         | NS        
-------------------------------------------------------------
1      | Nov 03-09     | Diana      | Julia      | Ethan     
2      | Nov 10-16     | Alice      | Laura      | Bob       
```

- **Week**: Sequential week number
- **Dates**: Date range (7 days from week start)
- **D/NP/NS**: Engineer assigned to each role

### CSV Export

```csv
Week,Role,Engineer,Start DateTime,End DateTime
1,Day Shift,Diana,2025-11-03 09:00,2025-11-03 17:00
1,Night Primary,Julia,2025-11-03 17:00,2025-11-04 09:00
1,Night Primary,Julia,2025-11-07 17:00,2025-11-10 09:00
```

Each row is an individual shift with exact times. Use cases:
- Tracking actual hours
- Importing to time-tracking systems
- Analyzing coverage patterns

### iCal Export

Import `schedule.ics` into:
- Google Calendar
- Apple Calendar
- Outlook
- Any iCalendar-compatible app

Each engineer's shifts appear as timed calendar events.

## Key Concepts

### Multi-Block Scheduling

For long-term schedules spanning multiple blocks, the system:
1. Solves Block 1 for the configured `weeks_per_block`
2. If `no_consecutive_weeks` rule is enabled:
   - Takes the engineers from the last week of Block 1
   - Marks them unavailable for week 1 of Block 2
3. Solves Block 2, and so on for all `num_blocks`

This prevents consecutive weeks across block boundaries (when `no_consecutive_weeks` is enabled).

**Example:** With `weeks_per_block: 8` and `num_blocks: 3`, you get a 24-week schedule solved in three 8-week chunks.

### Capacity Math

For a schedule to be feasible (per block):

```
engineers × max_shifts ≥ weeks_per_block × roles
```

**Example:**
- 12 engineers × 3 max_shifts = **36 capacity**
- 12 weeks_per_block × 3 roles = **36 demand** ✅
- Perfect balance!

**Another example:**
- 10 engineers × 4 max_shifts = **40 capacity**
- 8 weeks_per_block × 5 roles = **40 demand** ✅
- Also works!

The no-consecutive-weeks constraint further limits capacity. Use exact balance or slight surplus.

### Role Schedules

Roles define **when** coverage happens, e.g.:
- **Weeknight shifts**: 20:00 → 09:00 next day
- **Weekend shifts**: Fri 20:00 → Mon 09:00 (3 days!)
- **Day shifts**: Mon-Fri, 09:00-20:00 each day

The scheduler generates separate calendar events for each shift block.

## Advanced: Customizing Constraints

Enable or disable specific constraints in `config.yaml`:

```yaml
rules:
  no_consecutive_weeks: false  # Allow back-to-back weeks
  weekend_limit: false         # No limit on weekend shifts
```

Use this for testing or special scheduling scenarios.

## Troubleshooting

### "No feasible schedule found"

**Causes:**
1. Too many unavailability constraints
2. Insufficient capacity (check validation output)
3. Conflicting constraints

**Solutions:**
- Run `validate` to check capacity
- Reduce unavailability periods
- Increase `max_shifts_per_engineer`
- Add more engineers to the team

### Validation Fails

Check the error messages - they show exactly what is wrong:
- Missing required fields
- Invalid dates
- Insufficient capacity

### Schedule Changes Mid-Block

If you need to modify an existing schedule (e.g., someone gets sick):
- Update `availability.csv` with the new constraint
- Re-run `generate`
- The solver creates a new schedule respecting all constraints
