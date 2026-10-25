"""Entry point kept from the starter repo: runs the sample evaluation, custom cases and contract check."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate, custom_cases, validate_output

if __name__ == "__main__":
    evaluate.main("-v" in sys.argv)
    print()
    custom_cases.main()
    print()
    sys.argv = [sys.argv[0], "--samples"]
    sys.exit(validate_output.main())