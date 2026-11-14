operator = person "Operator" "Plans, reviews, and approves repository-local delivery." {
    properties {
        "cascade.semanticId" "element.person.operator"
    }
}

cascade = softwareSystem "Cascade" "Coordinates artifact-driven delivery in a Git repository." {
    properties {
        "cascade.semanticId" "element.system.cascade"
    }

    war_room = container "War Room" "Loopback operator UI and HTTP API." "Python HTTP" {
        properties {
            "cascade.semanticId" "element.container.war-room"
        }
    }

    supervisor = container "Service" "Runs lifecycle, teams, automation, and integration." "Python" {
        properties {
            "cascade.semanticId" "element.container.supervisor"
        }

        board_component = component "Board" "Parses and validates Markdown work state." "cascade.board" {
            properties {
                "cascade.semanticId" "element.component.board"
            }
        }
        agent_component = component "Agent runtime" "Normalizes provider turns and capability checks." "cascade.agent" {
            properties {
                "cascade.semanticId" "element.component.agent"
            }
        }
        team_component = component "Tier teams" "Runs persistent Epic/Feature and bounded Task graphs." "cascade.epic/feature/task" {
            properties {
                "cascade.semanticId" "element.component.teams"
            }
        }
        epic_team = component "Epic team" "Persistent manager and architect turns for strategic planning." "cascade.epic.graph" {
            properties {
                "cascade.semanticId" "element.component.epic-team"
            }
        }
        feature_team = component "Feature team" "Persistent lead and architect turns for Task planning and integration." "cascade.feature.graph" {
            properties {
                "cascade.semanticId" "element.component.feature-team"
            }
        }
        task_team = component "Task team" "Bounded SWE turns with scoped tools and supervised delivery." "cascade.task.graph" {
            properties {
                "cascade.semanticId" "element.component.task-team"
            }
        }
        watchdog_component = component "Watchdog" "Admits ready work and coordinates bounded recovery." "cascade.watchdog" {
            properties {
                "cascade.semanticId" "element.component.watchdog"
            }
        }
        boss_component = component "Boss" "Owns rollups, merge gates, and completion." "cascade.boss" {
            properties {
                "cascade.semanticId" "element.component.boss"
            }
        }
        workspace_component = component "Workspace" "Resolves repositories and revision-pinned architecture." "cascade.workspace" {
            properties {
                "cascade.semanticId" "element.component.workspace"
            }
        }
        collaboration_component = component "Comments and amendments" "Persists review routing and upward negotiation." "cascade.comments/amendments" {
            properties {
                "cascade.semanticId" "element.component.collaboration"
            }
        }
    }

    repository = container "Repository artifacts" "Git-backed board, designs, queues, and evidence." "Git + Markdown/JSON/DSL" {
        properties {
            "cascade.semanticId" "element.container.repository"
        }
    }
}

forge = softwareSystem "Git forge" "Hosts approval and Feature review boundaries." {
    properties {
        "cascade.semanticId" "element.system.forge"
    }
}

model_provider = softwareSystem "Model provider" "Executes bounded planning and implementation turns." {
    properties {
        "cascade.semanticId" "element.system.model-provider"
    }
}

structurizr = softwareSystem "Structurizr" "Produces local model artifacts." {
    properties {
        "cascade.semanticId" "element.system.structurizr"
    }

    structurizr_cli = container "Service" "Validates and exports the model." "Structurizr CLI" {
        properties {
            "cascade.semanticId" "element.container.structurizr-cli"
        }
    }
}

operator_uses_war_room = operator -> war_room "Uses" {
    properties {
        "cascade.semanticId" "relationship.operator-uses-war-room"
    }
}
war_room_calls_supervisor = war_room -> supervisor "Invokes authenticated operations" {
    properties {
        "cascade.semanticId" "relationship.war-room-calls-supervisor"
    }
}
supervisor_reads_repository = supervisor -> repository "Reads and commits canonical artifacts" {
    properties {
        "cascade.semanticId" "relationship.supervisor-reads-repository"
    }
}
agent_calls_provider = agent_component -> model_provider "Runs bounded turns" {
    properties {
        "cascade.semanticId" "relationship.agent-calls-provider"
    }
}
boss_uses_forge = boss_component -> forge "Publishes and observes reviews" {
    properties {
        "cascade.semanticId" "relationship.boss-uses-forge"
    }
}
workspace_calls_structurizr = workspace_component -> structurizr "Owns pinned model processing" {
    properties {
        "cascade.semanticId" "relationship.workspace-calls-structurizr"
    }
}
validates = supervisor -> structurizr_cli "Requests validation from" {
    properties {
        "cascade.semanticId" "relationship.supervisor-validates-with-cli"
    }
}
exports = supervisor -> structurizr_cli "Requests an isolated export from" {
    properties {
        "cascade.semanticId" "relationship.supervisor-exports-with-cli"
    }
}
watchdog_reads_board = watchdog_component -> board_component "Observes lifecycle state" {
    properties {
        "cascade.semanticId" "relationship.watchdog-reads-board"
    }
}
watchdog_dispatches_teams = watchdog_component -> team_component "Dispatches eligible work" {
    properties {
        "cascade.semanticId" "relationship.watchdog-dispatches-teams"
    }
}
teams_use_agent = team_component -> agent_component "Run role turns through" {
    properties {
        "cascade.semanticId" "relationship.teams-use-agent"
    }
}
teams_use_collaboration = team_component -> collaboration_component "Route comments and amendments through" {
    properties {
        "cascade.semanticId" "relationship.teams-use-collaboration"
    }
}
boss_reads_board = boss_component -> board_component "Computes gates and rollups from" {
    properties {
        "cascade.semanticId" "relationship.boss-reads-board"
    }
}
teams_use_workspace = team_component -> workspace_component "Use worktrees and architecture contracts" {
    properties {
        "cascade.semanticId" "relationship.teams-use-workspace"
    }
}

teams_route_epic = team_component -> epic_team "Routes scoped work to" {
    properties {
        "cascade.semanticId" "relationship.teams-route-epic"
    }
}

epic_runs_agent = epic_team -> agent_component "Executes role turns through" {
    properties {
        "cascade.semanticId" "relationship.epic-runs-agent"
    }
}

epic_persists = epic_team -> repository "Persists checkpoints and work evidence in" {
    properties {
        "cascade.semanticId" "relationship.epic-persists"
    }
}

teams_route_feature = team_component -> feature_team "Routes scoped work to" {
    properties {
        "cascade.semanticId" "relationship.teams-route-feature"
    }
}

feature_runs_agent = feature_team -> agent_component "Executes role turns through" {
    properties {
        "cascade.semanticId" "relationship.feature-runs-agent"
    }
}

feature_persists = feature_team -> repository "Persists checkpoints and work evidence in" {
    properties {
        "cascade.semanticId" "relationship.feature-persists"
    }
}

teams_route_task = team_component -> task_team "Routes scoped work to" {
    properties {
        "cascade.semanticId" "relationship.teams-route-task"
    }
}

task_runs_agent = task_team -> agent_component "Executes role turns through" {
    properties {
        "cascade.semanticId" "relationship.task-runs-agent"
    }
}

task_persists = task_team -> repository "Persists checkpoints and work evidence in" {
    properties {
        "cascade.semanticId" "relationship.task-persists"
    }
}

epic_coordinates_feature = epic_team -> feature_team "Plans and coordinates" {
    properties {
        "cascade.semanticId" "relationship.epic-coordinates-feature"
    }
}

feature_coordinates_task = feature_team -> task_team "Creates and coordinates" {
    properties {
        "cascade.semanticId" "relationship.feature-coordinates-task"
    }
}

operator_uses_cascade = operator -> cascade "Plans, reviews and approves delivery" {
    properties {
        "cascade.semanticId" "relationship.operator-uses-cascade"
    }
}

cascade_uses_provider = cascade -> model_provider "Executes bounded role turns" {
    properties {
        "cascade.semanticId" "relationship.cascade-uses-provider"
    }
}

cascade_uses_forge = cascade -> forge "Publishes and observes code reviews" {
    properties {
        "cascade.semanticId" "relationship.cascade-uses-forge"
    }
}

cascade_uses_renderer = cascade -> structurizr "Validates and renders local architecture" {
    properties {
        "cascade.semanticId" "relationship.cascade-uses-renderer"
    }
}
