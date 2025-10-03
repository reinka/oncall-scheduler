from ortools.sat.python import cp_model
from datetime import datetime, timedelta
from collections import defaultdict
import csv
import os


def parse_availability_csv(csv_path, schedule_start_date, num_blocks=2):
    """
    Parse availability CSV and convert to block/week constraints.
    
    CSV format: engineer,start_date,end_date
    Example: Diana,2025-11-24,2025-11-30
    
    Args:
        csv_path: path to CSV file
        schedule_start_date: first Monday of the schedule
        num_blocks: total number of 12-week blocks
    
    Returns:
        dict mapping (engineer, block, week) to False for unavailable periods
    """
    if not os.path.exists(csv_path):
        return {}
    
    constraints = {}
    total_weeks = num_blocks * 12
    
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
                    block = week_idx // 12
                    week_in_block = week_idx % 12
                    constraints[(engineer, block, week_in_block)] = False
    
    return constraints


def generate_on_call_schedule(start_date=None, availability_overrides=None, print_output=True):
    """
    Generates and prints a 12-week on-call schedule.
    
    Args:
        start_date: datetime object for the first Monday (default: Nov 3, 2025)
        availability_overrides: dict mapping (engineer, week) to False for unavailable weeks
        print_output: whether to print the schedule (default: True)
    
    Returns:
        dict: schedule[week][role] = engineer, or None if no solution found
    """
    # =================================================================
    # 1. INPUTS
    # =================================================================
    engineers = [
        'Alice', 'Bob', 'Charlie', 'Diana', 'Ethan', 'Fiona',
        'George', 'Hannah', 'Ian', 'Julia', 'Kevin', 'Laura'
    ]
    num_engineers = len(engineers)
    num_weeks = 12
    roles = ['D', 'NP', 'NS'] # Day, Night Primary, Night Secondary
    
    # Default start date: November 3, 2025 (Monday)
    if start_date is None:
        start_date = datetime(2025, 11, 3)

    # Availability: True if available, False if not.
    availability = {}
    for e in engineers:
        for w in range(num_weeks):
            availability[(e, w)] = True
    
    # Apply overrides if provided
    if availability_overrides:
        for (e, w), is_available in availability_overrides.items():
            availability[(e, w)] = is_available
    else:
        # Example: Diana is on vacation in Week 4 (week index 3)
        availability[('Diana', 3)] = False
        # Example: Bob is at a conference in Week 7 (week index 6)
        availability[('Bob', 6)] = False


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

    # C1: Roster Completeness
    # Each role must be filled exactly once per week.
    for w in range(num_weeks):
        for r in roles:
            model.AddExactlyOne(x[(e, w, r)] for e in engineers)

    # C2: No Consecutive Weeks
    # An engineer cannot work in two consecutive weeks.
    for e in engineers:
        for w in range(num_weeks - 1):
            work_in_week_w = sum(x[(e, w, r)] for r in roles)
            work_in_week_w1 = sum(x[(e, w + 1, r)] for r in roles)
            model.Add(work_in_week_w + work_in_week_w1 <= 1)

    # C3: Maximum Workload
    # Each engineer works at most 3 shifts in the period.
    # With T=12, W=12, this will be exactly 3.
    for e in engineers:
        total_shifts = sum(x[(e, w, r)] for w in range(num_weeks) for r in roles)
        model.Add(total_shifts <= 3)

    # C4: Weekend Limitation
    # Each engineer covers at most 1 weekend (Night Primary).
    for e in engineers:
        total_np_shifts = sum(x[(e, w, 'NP')] for w in range(num_weeks))
        model.Add(total_np_shifts <= 1)

    # C5: Role Separation per Week (Implicit in C1, but good practice)
    # An engineer holds at most one role per week.
    for e in engineers:
        for w in range(num_weeks):
            model.Add(sum(x[(e, w, r)] for r in roles) <= 1)
            
    # C6: Availability
    # An engineer can only be assigned if available.
    for e in engineers:
        for w in range(num_weeks):
            if not availability[(e, w)]:
                # If unavailable, they cannot be assigned any role this week.
                for r in roles:
                    model.Add(x[(e, w, r)] == 0)


    # =================================================================
    # 4. SOLVE
    # =================================================================
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0
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
            header = f"{'Week':<6} | {'Dates':<13} | {'Day':<10} | {'Night Primary':<15} | {'Night Secondary':<15}"
            print(header)
            print("-" * len(header))
            
            for w in range(num_weeks):
                week_start = start_date + timedelta(weeks=w)
                week_end = week_start + timedelta(days=6)
                date_range = f"{week_start.strftime('%b %d')}-{week_end.strftime('%d')}"
                day_eng = schedule[w]['D']
                np_eng = schedule[w]['NP']
                ns_eng = schedule[w]['NS']
                print(f"{(w+1):<6} | {date_range:<13} | {day_eng:<10} | {np_eng:<15} | {ns_eng:<15}")
        
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
            print(f"   - Total capacity with absences: {num_engineers * 3 - unavailable_count} person-shifts")
            print(f"   - Required capacity: {num_weeks * len(roles)} person-shifts")
            
            if (num_engineers * 3 - unavailable_count) < (num_weeks * len(roles)):
                print("   ⚠️  Insufficient capacity! Need to reduce absences or add engineers.")
        
        return None


def export_schedule_csv(schedules, start_date, output_path='schedule.csv'):
    """
    Export schedule to CSV format.
    
    Args:
        schedules: list of schedule dicts (one per block)
        start_date: datetime object for the first Monday
        output_path: path to output CSV file
    """
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Week', 'Start Date', 'End Date', 'Day', 'Night Primary', 'Night Secondary'])
        
        for block_idx, schedule in enumerate(schedules):
            for week in sorted(schedule.keys()):
                abs_week = block_idx * 12 + week + 1
                week_start = start_date + timedelta(weeks=block_idx * 12 + week)
                week_end = week_start + timedelta(days=6)
                
                writer.writerow([
                    abs_week,
                    week_start.strftime('%Y-%m-%d'),
                    week_end.strftime('%Y-%m-%d'),
                    schedule[week]['D'],
                    schedule[week]['NP'],
                    schedule[week]['NS']
                ])
    
    print(f"📄 Schedule exported to {output_path}")


def export_schedule_ical(schedules, start_date, output_path='schedule.ics'):
    """
    Export schedule to iCal format for calendar import.
    
    Args:
        schedules: list of schedule dicts (one per block)
        start_date: datetime object for the first Monday
        output_path: path to output ICS file
    """
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//On-Call Schedule//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:On-Call Schedule',
        'X-WR-TIMEZONE:UTC',
    ]
    
    role_names = {
        'D': 'Day Shift',
        'NP': 'Night Primary',
        'NS': 'Night Secondary'
    }
    
    for block_idx, schedule in enumerate(schedules):
        for week in sorted(schedule.keys()):
            week_start = start_date + timedelta(weeks=block_idx * 12 + week)
            week_end = week_start + timedelta(days=7)  # +7 for DTEND (exclusive)
            
            for role, role_name in role_names.items():
                engineer = schedule[week][role]
                
                lines.extend([
                    'BEGIN:VEVENT',
                    f'DTSTART;VALUE=DATE:{week_start.strftime("%Y%m%d")}',
                    f'DTEND;VALUE=DATE:{week_end.strftime("%Y%m%d")}',
                    f'SUMMARY:On-Call: {engineer} ({role_name})',
                    f'DESCRIPTION:Engineer: {engineer}\\nRole: {role_name}',
                    f'UID:{block_idx}-{week}-{role}@oncall',
                    'END:VEVENT',
                ])
    
    lines.append('END:VCALENDAR')
    
    with open(output_path, 'w') as f:
        f.write('\r\n'.join(lines))
    
    print(f"📅 Schedule exported to {output_path}")


def generate_multi_block_schedule(num_blocks=2, start_date=None, availability_overrides=None, availability_csv=None, export_formats=None):
    """
    Generates a multi-block schedule (e.g., 24 weeks = 2 blocks of 12 weeks).
    
    Args:
        num_blocks: number of 12-week blocks to schedule
        start_date: datetime object for the first Monday of block 1
        availability_overrides: dict mapping (engineer, block_idx, week) to False
        availability_csv: path to CSV file with unavailability dates
        export_formats: list of formats to export ['csv', 'ical'], or None for no export
    
    Returns:
        list of schedule dicts, one per block
    """
    if start_date is None:
        start_date = datetime(2025, 11, 3)
    
    # Parse CSV if provided and merge with overrides
    if availability_csv:
        csv_constraints = parse_availability_csv(availability_csv, start_date, num_blocks)
        if availability_overrides:
            csv_constraints.update(availability_overrides)
        availability_overrides = csv_constraints
    
    schedules = []
    boundary_constraints = {}
    
    for block_idx in range(num_blocks):
        print(f"\n{'='*60}")
        print(f"BLOCK {block_idx + 1} (Weeks {block_idx*12 + 1}-{(block_idx+1)*12})")
        print(f"{'='*60}\n")
        
        # Calculate start date for this block
        block_start = start_date + timedelta(weeks=12 * block_idx)
        
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
            start_date=block_start,
            availability_overrides=block_availability if block_availability else None,
            print_output=True
        )
        
        if schedule is None:
            print(f"\n❌ Failed to generate schedule for block {block_idx + 1}")
            return None
        
        schedules.append(schedule)
        
        # Extract week 11 (last week) engineers for next block's boundary
        if block_idx < num_blocks - 1:
            boundary_constraints = {}
            for role in ['D', 'NP', 'NS']:
                engineer = schedule[11][role]  # Week 11 is the last week (0-indexed)
                boundary_constraints[(engineer, 0)] = False  # Block next week 0
    
    # Export if requested
    if export_formats and schedules:
        print(f"\n{'='*60}")
        print("EXPORTING SCHEDULE")
        print(f"{'='*60}\n")
        
        if 'csv' in export_formats:
            export_schedule_csv(schedules, start_date)
        if 'ical' in export_formats:
            export_schedule_ical(schedules, start_date)
    
    return schedules


if __name__ == '__main__':
    generate_multi_block_schedule(
        availability_csv='availability.csv',
        export_formats=['csv', 'ical']
    )