from ortools.sat.python import cp_model
from datetime import datetime, timedelta
from collections import defaultdict
import csv
import os
import yaml

# Constants
SEPARATOR = '=' * 60


def load_config(config_path='config.yaml'):
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def parse_availability_csv(csv_path, schedule_start_date, num_blocks=2, weeks_per_block=12):
    """
    Parse availability CSV and convert to block/week constraints.
    
    CSV format: engineer,start_date,end_date
    Example: Diana,2025-11-24,2025-11-30
    
    Args:
        csv_path: path to CSV file
        schedule_start_date: first Monday of the schedule
        num_blocks: total number of blocks
        weeks_per_block: weeks per block
    
    Returns:
        dict mapping (engineer, block, week) to False for unavailable periods
    """
    if not os.path.exists(csv_path):
        return {}
    
    constraints = {}
    total_weeks = num_blocks * weeks_per_block
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            engineer = row['engineer'].strip()
            start = datetime.strptime(row['start_date'].strip(), '%Y-%m-%d')
            end = datetime.strptime(row['end_date'].strip(), '%Y-%m-%d')
            
            # Find which weeks this date range overlaps
            for week_idx in range(total_weeks):
                week_start = schedule_start_date + timedelta(weeks=week_idx)
                week_end = week_start + timedelta(days=6)
                
                # Check if unavailable period overlaps this week
                if start <= week_end and end >= week_start:
                    block = week_idx // weeks_per_block
                    week_in_block = week_idx % weeks_per_block
                    constraints[(engineer, block, week_in_block)] = False
    
    return constraints


def add_roster_completeness(model, x, engineers, roles, num_weeks):
    """C1: Each role must be filled exactly once per week."""
    for w in range(num_weeks):
        for r in roles:
            model.AddExactlyOne(x[(e, w, r)] for e in engineers)


def add_no_consecutive_weeks(model, x, engineers, roles, num_weeks):
    """C2: An engineer cannot work in two consecutive weeks."""
    for e in engineers:
        for w in range(num_weeks - 1):
            work_in_week_w = sum(x[(e, w, r)] for r in roles)
            work_in_week_w1 = sum(x[(e, w + 1, r)] for r in roles)
            model.Add(work_in_week_w + work_in_week_w1 <= 1)


def add_max_workload(model, x, engineers, roles, num_weeks, max_shifts):
    """C3: Each engineer works at most max_shifts in the period."""
    for e in engineers:
        total_shifts = sum(x[(e, w, r)] for w in range(num_weeks) for r in roles)
        model.Add(total_shifts <= max_shifts)


def add_weekend_limit(model, x, engineers, num_weeks, max_weekends, weekend_role):
    """C4: Each engineer covers at most max_weekends in the weekend role."""
    for e in engineers:
        total_weekend_shifts = sum(x[(e, w, weekend_role)] for w in range(num_weeks))
        model.Add(total_weekend_shifts <= max_weekends)


def add_role_separation(model, x, engineers, roles, num_weeks):
    """C5: An engineer holds at most one role per week."""
    for e in engineers:
        for w in range(num_weeks):
            model.Add(sum(x[(e, w, r)] for r in roles) <= 1)


def add_availability(model, x, engineers, roles, num_weeks, availability):
    """C6: An engineer can only be assigned if available."""
    for e in engineers:
        for w in range(num_weeks):
            if not availability[(e, w)]:
                for r in roles:
                    model.Add(x[(e, w, r)] == 0)


def generate_on_call_schedule(engineers, roles, start_date, num_weeks=12, max_shifts=3, max_weekends=1, weekend_role='NP', solver_timeout=60.0, availability_overrides=None, active_rules=None, print_output=True):
    """
    Generates and prints an on-call schedule.
    
    Args:
        engineers: list of engineer names
        roles: list of role codes (e.g., ['D', 'NP', 'NS'])
        start_date: datetime object for the first Monday
        num_weeks: number of weeks in the schedule block
        max_shifts: maximum shifts per engineer in the period
        max_weekends: maximum weekend shifts per engineer
        weekend_role: which role represents weekend coverage
        solver_timeout: maximum solver time in seconds
        availability_overrides: dict mapping (engineer, week) to False for unavailable weeks
        active_rules: dict of rule names to bool (which constraints to apply)
        print_output: whether to print the schedule (default: True)
    
    Returns:
        dict: schedule[week][role] = engineer, or None if no solution found
    """
    # =================================================================
    # 1. INPUTS
    # =================================================================
    num_engineers = len(engineers)

    # Availability: True if available, False if not.
    availability = {}
    for e in engineers:
        for w in range(num_weeks):
            availability[(e, w)] = True
    
    # Apply overrides if provided
    if availability_overrides:
        for (e, w), is_available in availability_overrides.items():
            availability[(e, w)] = is_available


    # =================================================================
    # 2. MODEL CREATION
    # =================================================================
    model = cp_model.CpModel()

    # Create the x_{e,w,r} variables.
    # x[(e, w, r)] is 1 if engineer e is assigned role r in week w, and 0 otherwise.
    x = {}
    for e in engineers:
        for w in range(num_weeks):
            for r in roles:
                x[(e, w, r)] = model.NewBoolVar(f'x_{e}_{w}_{r}')


    # =================================================================
    # 3. ADDING CONSTRAINTS
    # =================================================================
    
    # Default: all rules active if not specified
    if active_rules is None:
        active_rules = {
            'roster_completeness': True,
            'no_consecutive_weeks': True,
            'max_workload': True,
            'weekend_limit': True,
            'role_separation': True,
            'availability': True
        }
    
    # Rule dispatch table
    rule_functions = {
        'roster_completeness': lambda: add_roster_completeness(model, x, engineers, roles, num_weeks),
        'no_consecutive_weeks': lambda: add_no_consecutive_weeks(model, x, engineers, roles, num_weeks),
        'max_workload': lambda: add_max_workload(model, x, engineers, roles, num_weeks, max_shifts),
        'weekend_limit': lambda: add_weekend_limit(model, x, engineers, num_weeks, max_weekends, weekend_role),
        'role_separation': lambda: add_role_separation(model, x, engineers, roles, num_weeks),
        'availability': lambda: add_availability(model, x, engineers, roles, num_weeks, availability)
    }
    
    # Apply active rules
    for rule_name, is_active in active_rules.items():
        if is_active and rule_name in rule_functions:
            rule_functions[rule_name]()


    # =================================================================
    # 4. SOLVE
    # =================================================================
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = solver_timeout
    status = solver.Solve(model)


    # =================================================================
    # 5. EXTRACT AND PRINT THE OUTPUT
    # =================================================================
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        # Create a schedule data structure
        schedule = {}
        for w in range(num_weeks):
            schedule[w] = {}
            for r in roles:
                for e in engineers:
                    if solver.Value(x[(e, w, r)]) == 1:
                        schedule[w][r] = e
        
        if print_output:
            print("✅ Feasible schedule found!\n")
            # Print the formatted schedule
            role_columns = ' | '.join([f"{r:<10}" for r in roles])
            header = f"{'Week':<6} | {'Dates':<13} | {role_columns}"
            print(header)
            print("-" * len(header))
            
            for w in range(num_weeks):
                week_start = start_date + timedelta(weeks=w)
                week_end = week_start + timedelta(days=6)
                date_range = f"{week_start.strftime('%b %d')}-{week_end.strftime('%d')}"
                role_values = ' | '.join([f"{schedule[w][r]:<10}" for r in roles])
                print(f"{(w+1):<6} | {date_range:<13} | {role_values}")
        
        return schedule

    else:
        if print_output:
            print("❌ No feasible schedule found.")
            print(f"⏱️  Solver time: {solver.WallTime():.3f} seconds")
            print("\n📋 Possible reasons:")
            print("   - Too many unavailability constraints (capacity < demand)")
            print("   - Constraint conflicts (e.g., consecutive week deadlock)")
            print("   - Try reducing absences or increasing team size")
            print("\n💡 Suggestions:")
            
            # Count unavailable slots
            unavailable_count = sum(1 for (e, w) in availability if not availability[(e, w)])
            print(f"   - Current unavailable slots: {unavailable_count}")
            print(f"   - Total capacity: {num_engineers * max_shifts} person-shifts (max)")
            print(f"   - Required capacity: {num_weeks * len(roles)} person-shifts")
            print(f"   - Note: No-consecutive-weeks constraint further limits capacity")
            
            if (num_engineers * max_shifts - unavailable_count) < (num_weeks * len(roles)):
                print("   ⚠️  Insufficient capacity! Need to reduce absences or add engineers.")
        
        return None


def generate_shift_events(schedules, start_date, roles, role_definitions, weeks_per_block=12):
    """
    Generate individual shift events with exact start/end times.
    
    Args:
        schedules: list of schedule dicts (one per block)
        start_date: datetime object for the first Monday
        roles: list of role codes
        role_definitions: dict with role schedules
        weeks_per_block: weeks per block
    
    Yields:
        dict with: block_idx, week, abs_week, role, role_name, engineer, 
                   day_name, event_start, event_end
    """
    # Map day names to weekday numbers (0=Monday)
    day_map = {'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6}
    
    for block_idx, schedule in enumerate(schedules):
        for week in sorted(schedule.keys()):
            abs_week = block_idx * weeks_per_block + week + 1
            week_monday = start_date + timedelta(weeks=block_idx * weeks_per_block + week)
            
            for role in roles:
                engineer = schedule[week][role]
                role_def = role_definitions[role]
                role_name = role_def.get('name', role)
                schedule_blocks = role_def.get('schedule', [])
                
                for block in schedule_blocks:
                    days = block['days']
                    start_time = block['start_time']
                    end_time = block['end_time']
                    span_days = block.get('span_days', 1)
                    
                    for day_name in days:
                        day_offset = day_map[day_name]
                        event_start_date = week_monday + timedelta(days=day_offset)
                        
                        # Parse times
                        start_hour, start_min = map(int, start_time.split(':'))
                        end_hour, end_min = map(int, end_time.split(':'))
                        
                        # Create start datetime
                        event_start = event_start_date.replace(hour=start_hour, minute=start_min)
                        
                        # Calculate end datetime
                        if span_days > 1:
                            # Multi-day event (e.g., Fri 17:00 -> Mon 09:00)
                            event_end = event_start + timedelta(days=span_days, hours=0, minutes=0)
                            event_end = event_end.replace(hour=end_hour, minute=end_min)
                        elif end_hour < start_hour or (end_hour == start_hour and end_min < start_min):
                            # Overnight event (e.g., 17:00 -> 09:00 next day)
                            event_end = event_start + timedelta(days=1)
                            event_end = event_end.replace(hour=end_hour, minute=end_min)
                        else:
                            # Same day event
                            event_end = event_start.replace(hour=end_hour, minute=end_min)
                        
                        yield {
                            'block_idx': block_idx,
                            'week': week,
                            'abs_week': abs_week,
                            'role': role,
                            'role_name': role_name,
                            'engineer': engineer,
                            'day_name': day_name,
                            'event_start': event_start,
                            'event_end': event_end
                        }


def export_schedule_csv(schedules, start_date, roles, role_definitions, weeks_per_block=12, output_path='schedule.csv'):
    """
    Export schedule to CSV format with detailed time information.
    
    Args:
        schedules: list of schedule dicts (one per block)
        start_date: datetime object for the first Monday
        roles: list of role codes
        role_definitions: dict with role schedules
        weeks_per_block: weeks per block
        output_path: path to output CSV file
    """
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Week', 'Role', 'Engineer', 'Start DateTime', 'End DateTime'])
        
        for event in generate_shift_events(schedules, start_date, roles, role_definitions, weeks_per_block):
            writer.writerow([
                event['abs_week'],
                event['role_name'],
                event['engineer'],
                event['event_start'].strftime('%Y-%m-%d %H:%M'),
                event['event_end'].strftime('%Y-%m-%d %H:%M')
            ])
    
    print(f"📄 Schedule exported to {output_path}")


def export_schedule_ical(schedules, start_date, roles, role_definitions, timezone='UTC', weeks_per_block=12, output_path='schedule.ics'):
    """
    Export schedule to iCal format for calendar import with timed events.
    
    Args:
        schedules: list of schedule dicts (one per block)
        start_date: datetime object for the first Monday
        roles: list of role codes
        role_definitions: dict with role schedules
        timezone: timezone string
        weeks_per_block: weeks per block
        output_path: path to output ICS file
    """
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//On-Call Schedule//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:On-Call Schedule',
        f'X-WR-TIMEZONE:{timezone}',
    ]
    
    for event in generate_shift_events(schedules, start_date, roles, role_definitions, weeks_per_block):
        start_str = event['event_start'].strftime('%Y%m%dT%H%M%S')
        end_str = event['event_end'].strftime('%Y%m%dT%H%M%S')
        
        lines.extend([
            'BEGIN:VEVENT',
            f'DTSTART:{start_str}',
            f'DTEND:{end_str}',
            f'SUMMARY:On-Call: {event["engineer"]} ({event["role_name"]})',
            f'DESCRIPTION:Engineer: {event["engineer"]}\\nRole: {event["role_name"]}',
            f'UID:{event["block_idx"]}-{event["week"]}-{event["role"]}-{event["day_name"]}@oncall',
            'END:VEVENT',
        ])
    
    lines.append('END:VCALENDAR')
    
    with open(output_path, 'w') as f:
        f.write('\r\n'.join(lines))
    
    print(f"📅 Schedule exported to {output_path}")


def generate_multi_block_schedule(config):
    """
    Generates a multi-block schedule from configuration.
    
    Args:
        config: dict with configuration (from YAML/JSON file)
    
    Returns:
        list of schedule dicts, one per block
    """
    # Extract config values
    engineers = config['team']
    roles_config = config['roles']
    roles = list(roles_config.keys())
    role_definitions = roles_config
    
    start_date = datetime.strptime(config['schedule']['start_date'], '%Y-%m-%d')
    num_blocks = config['schedule']['num_blocks']
    weeks_per_block = config['schedule'].get('weeks_per_block', 12)  # Default to 12
    timezone = config['schedule'].get('timezone', 'UTC')
    max_shifts = config['constraints']['max_shifts_per_engineer']
    max_weekends = config['constraints']['max_weekends_per_engineer']
    weekend_role = config['constraints'].get('weekend_role', 'NP')  # Default to 'NP'
    solver_timeout = config.get('solver', {}).get('timeout_seconds', 60.0)  # Default to 60
    availability_csv = config['files']['availability_csv']
    export_formats = config['files']['export_formats']
    active_rules = config.get('rules', None)  # Optional rules section
    
    availability_overrides = None
    
    # Parse CSV if provided and merge with overrides
    if availability_csv:
        csv_constraints = parse_availability_csv(availability_csv, start_date, num_blocks, weeks_per_block)
        if availability_overrides:
            csv_constraints.update(availability_overrides)
        availability_overrides = csv_constraints
    
    schedules = []
    boundary_constraints = {}
    
    for block_idx in range(num_blocks):
        print(f"\n{SEPARATOR}")
        print(f"BLOCK {block_idx + 1} (Weeks {block_idx*weeks_per_block + 1}-{(block_idx+1)*weeks_per_block})")
        print(f"{SEPARATOR}\n")
        
        # Calculate start date for this block
        block_start = start_date + timedelta(weeks=weeks_per_block * block_idx)
        
        # Merge availability: user overrides + boundary constraints
        block_availability = {}
        if availability_overrides:
            for (e, b, w), available in availability_overrides.items():
                if b == block_idx:
                    block_availability[(e, w)] = available
        
        # Add boundary constraint from previous block
        block_availability.update(boundary_constraints)
        
        # Generate schedule for this block
        schedule = generate_on_call_schedule(
            engineers=engineers,
            roles=roles,
            start_date=block_start,
            num_weeks=weeks_per_block,
            max_shifts=max_shifts,
            max_weekends=max_weekends,
            weekend_role=weekend_role,
            solver_timeout=solver_timeout,
            availability_overrides=block_availability if block_availability else None,
            active_rules=active_rules,
            print_output=True
        )
        
        if schedule is None:
            print(f"\n❌ Failed to generate schedule for block {block_idx + 1}")
            return None
        
        schedules.append(schedule)
        
        # Extract last week engineers for next block's boundary
        if block_idx < num_blocks - 1:
            boundary_constraints = {}
            last_week = weeks_per_block - 1  # 0-indexed
            for role in roles:
                engineer = schedule[last_week][role]
                boundary_constraints[(engineer, 0)] = False  # Block next week 0
    
    # Export if requested
    if export_formats and schedules:
        print(f"\n{SEPARATOR}")
        print("EXPORTING SCHEDULE")
        print(f"{SEPARATOR}\n")
        
        if 'csv' in export_formats:
            export_schedule_csv(schedules, start_date, roles, role_definitions, weeks_per_block)
        if 'ical' in export_formats:
            export_schedule_ical(schedules, start_date, roles, role_definitions, timezone, weeks_per_block)
    
    return schedules


if __name__ == '__main__':
    config = load_config('config.yaml')
    generate_multi_block_schedule(config)