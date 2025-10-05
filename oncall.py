#!/usr/bin/env python3
"""
On-Call Schedule Generator CLI

Usage:
    ./oncall.py generate --config config.yaml
    ./oncall.py validate --config config.yaml
"""

import argparse
import sys
import os
from pathlib import Path
from solver import (
    load_config,
    generate_multi_block_schedule,
    SEPARATOR
)


def cmd_generate(args):
    """Generate on-call schedule."""
    if not os.path.exists(args.config):
        print(f"❌ Config file not found: {args.config}")
        sys.exit(1)
    
    print(f"📋 Loading config from: {args.config}")
    config = load_config(args.config)
    
    # Override output directory if specified
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Update file paths in config
        if 'csv' in config['files']['export_formats']:
            config['_csv_output'] = str(output_dir / 'schedule.csv')
        if 'ical' in config['files']['export_formats']:
            config['_ical_output'] = str(output_dir / 'schedule.ics')
    
    print(f"🚀 Generating schedule...")
    schedules = generate_multi_block_schedule(config)
    
    if schedules:
        print(f"\n✅ Schedule generated successfully!")
        sys.exit(0)
    else:
        print(f"\n❌ Failed to generate schedule")
        sys.exit(1)


def cmd_validate(args):
    """Validate configuration file."""
    if not os.path.exists(args.config):
        print(f"❌ Config file not found: {args.config}")
        sys.exit(1)
    
    print(f"📋 Validating config: {args.config}")
    
    try:
        config = load_config(args.config)
        
        # Basic validation
        errors = []
        
        # Check required sections
        required_sections = ['team', 'roles', 'schedule', 'constraints', 'files']
        for section in required_sections:
            if section not in config:
                errors.append(f"Missing required section: '{section}'")
        
        if not errors:
            # Validate team
            team = config.get('team', [])
            if not isinstance(team, list) or len(team) == 0:
                errors.append("'team' must be a non-empty list")
            
            # Validate roles
            roles_config = config.get('roles', {})
            if not isinstance(roles_config, dict) or len(roles_config) == 0:
                errors.append("'roles' must be a non-empty dict")
            
            # Validate schedule section
            schedule = config.get('schedule', {})
            if 'start_date' not in schedule:
                errors.append("'schedule.start_date' is required")
            else:
                # Validate date format
                try:
                    from datetime import datetime
                    _ = datetime.strptime(schedule['start_date'], '%Y-%m-%d')
                except ValueError:
                    errors.append(f"'schedule.start_date' has invalid date format: {schedule['start_date']} (expected YYYY-MM-DD)")
            if 'num_blocks' not in schedule:
                errors.append("'schedule.num_blocks' is required")
            if 'weeks_per_block' not in schedule:
                errors.append("'schedule.weeks_per_block' is required")
            
            # Validate constraints
            constraints = config.get('constraints', {})
            if 'max_shifts_per_engineer' not in constraints:
                errors.append("'constraints.max_shifts_per_engineer' is required")
            if 'max_weekends_per_engineer' not in constraints:
                errors.append("'constraints.max_weekends_per_engineer' is required")
            
            # Capacity check (per block)
            if not errors:
                num_engineers = len(team)
                weeks_per_block = schedule['weeks_per_block']
                num_blocks = schedule['num_blocks']
                num_roles = len(roles_config)
                max_shifts = constraints['max_shifts_per_engineer']
                
                # Capacity is per-block since we solve sequentially
                required_per_block = weeks_per_block * num_roles
                available_per_block = num_engineers * max_shifts
                
                print(f"\n📊 Capacity Analysis:")
                print(f"   Engineers: {num_engineers}")
                print(f"   Blocks: {num_blocks} × {weeks_per_block} weeks each")
                print(f"   Roles per week: {num_roles}")
                print(f"   Required per block: {required_per_block} person-shifts")
                print(f"   Available per block: {available_per_block} person-shifts (max)")
                
                if available_per_block < required_per_block:
                    errors.append(f"Insufficient capacity per block! Need {required_per_block} but only have {available_per_block}")
        
        if errors:
            print(f"\n❌ Validation failed:\n")
            for error in errors:
                print(f"   • {error}")
            sys.exit(1)
        else:
            print(f"\n✅ Configuration is valid!")
            sys.exit(0)
    
    except Exception as e:
        print(f"\n❌ Error loading config: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='On-Call Schedule Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s generate --config config.yaml
  %(prog)s generate --config config.yaml --output-dir schedules/
  %(prog)s validate --config config.yaml
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    subparsers.required = True
    
    # Generate command
    parser_generate = subparsers.add_parser('generate', help='Generate on-call schedule')
    parser_generate.add_argument('--config', '-c', default='config.yaml',
                                  help='Path to config file (default: config.yaml)')
    parser_generate.add_argument('--output-dir', '-o',
                                  help='Output directory for generated files')
    parser_generate.set_defaults(func=cmd_generate)
    
    # Validate command
    parser_validate = subparsers.add_parser('validate', help='Validate configuration')
    parser_validate.add_argument('--config', '-c', default='config.yaml',
                                  help='Path to config file (default: config.yaml)')
    parser_validate.set_defaults(func=cmd_validate)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()

