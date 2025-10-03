from ortools.sat.python import cp_model
from datetime import datetime, timedelta
from collections import defaultdict

def generate_on_call_schedule(start_date=None, availability_overrides=None):
    """
    Generates and prints a 12-week on-call schedule.
    
    Args:
        start_date: datetime object for the first Monday (default: Nov 3, 2025)
        availability_overrides: dict mapping (engineer, week) to False for unavailable weeks
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
    # 5. PRINT THE OUTPUT
    # =================================================================
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print("✅ Feasible schedule found!\n")
        
        # Create a schedule data structure for easy printing
        schedule = {}
        for w in range(num_weeks):
            schedule[w] = {}
            for r in roles:
                for e in engineers:
                    if solver.Value(x[(e, w, r)]) == 1:
                        schedule[w][r] = e
        
        # Print the formatted schedule
        header = f"{'Week':<6} | {'Day':<10} | {'Night Primary':<15} | {'Night Secondary':<15}"
        print(header)
        print("-" * len(header))
        
        for w in range(num_weeks):
            day_eng = schedule[w]['D']
            np_eng = schedule[w]['NP']
            ns_eng = schedule[w]['NS']
            print(f"{(w+1):<6} | {day_eng:<10} | {np_eng:<15} | {ns_eng:<15}")

    else:
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


if __name__ == '__main__':
    generate_on_call_schedule()