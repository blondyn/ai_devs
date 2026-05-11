from pathlib import Path
from s02e04.agent import run_agent

WORKFLOW = (Path(__file__).parent / "agents" / "workflow.md").read_text()


def main():
    result = run_agent("orchestrator", WORKFLOW)
    print(result)


if __name__ == "__main__":
    main()
