#!/usr/bin/env python3
"""Run the full offline analytics pipeline."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analytics.topic_evolution import run as run_topic_evolution
from analytics.emerging_topics import run as run_emerging_topics
from analytics.collaboration_network import run as run_collaboration
from analytics.paper_clustering import run as run_clustering


def main():
    run_topic_evolution()
    print()
    run_emerging_topics()
    print()
    run_collaboration()
    print()
    run_clustering()


if __name__ == "__main__":
    main()
