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

code_epic_graph = element "epic: ensure_epic_graph" "Function" "Compiles sequential role nodes with LangGraph StateGraph." {
    properties {
        "cascade.semanticId" "element.code.epic.graph"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/epic/graph.py"
        "cascade.sourceSymbol" "ensure_epic_graph"
    }
}

code_epic_state = element "epic: EpicGraphState" "TypedDict" "Messages, queue cursor and role configuration survive turns." {
    properties {
        "cascade.semanticId" "element.code.epic.state"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/epic/state.py"
        "cascade.sourceSymbol" "EpicGraphState"
    }
}

code_epic_checkpoint = element "epic: get_checkpointer" "Function / SqliteSaver" "langgraph-checkpoint-sqlite stores one SQLite file per work ID." {
    properties {
        "cascade.semanticId" "element.code.epic.checkpoint"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/epic/checkpoint.py"
        "cascade.sourceSymbol" "get_checkpointer"
    }
}

code_epic_wiring = element "epic: load_epic_tools" "Function" "Registers scoped tools and lifecycle hooks." {
    properties {
        "cascade.semanticId" "element.code.epic.wiring"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/epic/wiring.py"
        "cascade.sourceSymbol" "load_epic_tools"
    }
}

code_epic_registry = element "epic: epic_tools" "Function" "Maps approved tool names to work-scoped callables." {
    properties {
        "cascade.semanticId" "element.code.epic.registry"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/epic/registry.py"
        "cascade.sourceSymbol" "epic_tools"
    }
}

code_epic_guard = element "epic: tool_guard" "Function" "Checks Cascade tool paths and work scope; not an OS sandbox." {
    properties {
        "cascade.semanticId" "element.code.epic.guard"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/epic/guard.py"
        "cascade.sourceSymbol" "tool_guard"
    }
}

code_epic_runtime = element "epic: run_planning_role_turn" "Function" "Builds bounded provider turns and MCP tools. Provider permissions govern native tools." {
    properties {
        "cascade.semanticId" "element.code.epic.runtime"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/agent/graph_turn.py"
        "cascade.sourceSymbol" "run_planning_role_turn"
    }
}

code_epic_provider = element "epic: build_codex_argv" "Provider adapter" "Planning uses provider-default permissions unless yolo bypasses sandboxing; other providers differ." {
    properties {
        "cascade.semanticId" "element.code.epic.provider"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/agent/codex_cli.py"
        "cascade.sourceSymbol" "build_codex_argv"
    }
}

code_epic_rel_29 = code_epic_graph -> code_epic_state "Uses typed state" {
    properties {
        "cascade.semanticId" "relationship.code-epic-graph-to-code-epic-state"
    }
}

code_epic_rel_30 = code_epic_graph -> code_epic_checkpoint "Compiles with persistent checkpointer" {
    properties {
        "cascade.semanticId" "relationship.code-epic-graph-to-code-epic-checkpoint"
    }
}

code_epic_rel_31 = code_epic_graph -> code_epic_runtime "Executes role turns sequentially" {
    properties {
        "cascade.semanticId" "relationship.code-epic-graph-to-code-epic-runtime"
    }
}

code_epic_rel_32 = code_epic_wiring -> code_epic_registry "Registers tools" {
    properties {
        "cascade.semanticId" "relationship.code-epic-wiring-to-code-epic-registry"
    }
}

code_epic_rel_33 = code_epic_runtime -> code_epic_registry "Exposes scoped tool calls" {
    properties {
        "cascade.semanticId" "relationship.code-epic-runtime-to-code-epic-registry"
    }
}

code_epic_rel_34 = code_epic_registry -> code_epic_guard "Tool implementations enforce scope" {
    properties {
        "cascade.semanticId" "relationship.code-epic-registry-to-code-epic-guard"
    }
}

code_epic_rel_35 = code_epic_runtime -> code_epic_provider "Dispatches through selected adapter" {
    properties {
        "cascade.semanticId" "relationship.code-epic-runtime-to-code-epic-provider"
    }
}

code_feature_graph = element "feature: ensure_feature_graph" "Function" "Compiles sequential role nodes with LangGraph StateGraph." {
    properties {
        "cascade.semanticId" "element.code.feature.graph"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/graph.py"
        "cascade.sourceSymbol" "ensure_feature_graph"
    }
}

code_feature_state = element "feature: FeatureGraphState" "TypedDict" "Messages, queue cursor and role configuration survive turns." {
    properties {
        "cascade.semanticId" "element.code.feature.state"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/state.py"
        "cascade.sourceSymbol" "FeatureGraphState"
    }
}

code_feature_checkpoint = element "feature: get_checkpointer" "Function / SqliteSaver" "langgraph-checkpoint-sqlite stores one SQLite file per work ID." {
    properties {
        "cascade.semanticId" "element.code.feature.checkpoint"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/checkpoint.py"
        "cascade.sourceSymbol" "get_checkpointer"
    }
}

code_feature_wiring = element "feature: load_feature_tools" "Function" "Registers scoped tools and lifecycle hooks." {
    properties {
        "cascade.semanticId" "element.code.feature.wiring"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/wiring.py"
        "cascade.sourceSymbol" "load_feature_tools"
    }
}

code_feature_registry = element "feature: feature_tools" "Function" "Maps approved tool names to work-scoped callables." {
    properties {
        "cascade.semanticId" "element.code.feature.registry"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/registry.py"
        "cascade.sourceSymbol" "feature_tools"
    }
}

code_feature_guard = element "feature: tool_guard" "Function" "Checks Cascade tool paths and work scope; not an OS sandbox." {
    properties {
        "cascade.semanticId" "element.code.feature.guard"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/guard.py"
        "cascade.sourceSymbol" "tool_guard"
    }
}

code_feature_runtime = element "feature: run_planning_role_turn" "Function" "Builds bounded provider turns and MCP tools. Provider permissions govern native tools." {
    properties {
        "cascade.semanticId" "element.code.feature.runtime"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/agent/graph_turn.py"
        "cascade.sourceSymbol" "run_planning_role_turn"
    }
}

code_feature_provider = element "feature: build_codex_argv" "Provider adapter" "Planning uses provider-default permissions unless yolo bypasses sandboxing; other providers differ." {
    properties {
        "cascade.semanticId" "element.code.feature.provider"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/agent/codex_cli.py"
        "cascade.sourceSymbol" "build_codex_argv"
    }
}

code_feature_rel_36 = code_feature_graph -> code_feature_state "Uses typed state" {
    properties {
        "cascade.semanticId" "relationship.code-feature-graph-to-code-feature-state"
    }
}

code_feature_rel_37 = code_feature_graph -> code_feature_checkpoint "Compiles with persistent checkpointer" {
    properties {
        "cascade.semanticId" "relationship.code-feature-graph-to-code-feature-checkpoint"
    }
}

code_feature_rel_38 = code_feature_graph -> code_feature_runtime "Executes role turns sequentially" {
    properties {
        "cascade.semanticId" "relationship.code-feature-graph-to-code-feature-runtime"
    }
}

code_feature_rel_39 = code_feature_wiring -> code_feature_registry "Registers tools" {
    properties {
        "cascade.semanticId" "relationship.code-feature-wiring-to-code-feature-registry"
    }
}

code_feature_rel_40 = code_feature_runtime -> code_feature_registry "Exposes scoped tool calls" {
    properties {
        "cascade.semanticId" "relationship.code-feature-runtime-to-code-feature-registry"
    }
}

code_feature_rel_41 = code_feature_registry -> code_feature_guard "Tool implementations enforce scope" {
    properties {
        "cascade.semanticId" "relationship.code-feature-registry-to-code-feature-guard"
    }
}

code_feature_rel_42 = code_feature_runtime -> code_feature_provider "Dispatches through selected adapter" {
    properties {
        "cascade.semanticId" "relationship.code-feature-runtime-to-code-feature-provider"
    }
}

code_task_graph = element "task: ensure_task_graph" "Function" "Compiles sequential role nodes with LangGraph StateGraph." {
    properties {
        "cascade.semanticId" "element.code.task.graph"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/graph.py"
        "cascade.sourceSymbol" "ensure_task_graph"
    }
}

code_task_state = element "task: TaskGraphState" "TypedDict" "Messages, queue cursor and role configuration survive turns." {
    properties {
        "cascade.semanticId" "element.code.task.state"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/state.py"
        "cascade.sourceSymbol" "TaskGraphState"
    }
}

code_task_checkpoint = element "task: get_checkpointer" "Function / SqliteSaver" "langgraph-checkpoint-sqlite stores one SQLite file per work ID." {
    properties {
        "cascade.semanticId" "element.code.task.checkpoint"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/checkpoint.py"
        "cascade.sourceSymbol" "get_checkpointer"
    }
}

code_task_wiring = element "task: load_task_tools" "Function" "Registers scoped tools and lifecycle hooks." {
    properties {
        "cascade.semanticId" "element.code.task.wiring"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/wiring.py"
        "cascade.sourceSymbol" "load_task_tools"
    }
}

code_task_registry = element "task: task_tools" "Function" "Maps approved tool names to work-scoped callables." {
    properties {
        "cascade.semanticId" "element.code.task.registry"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/registry.py"
        "cascade.sourceSymbol" "task_tools"
    }
}

code_task_guard = element "task: task_tool_guard" "Function" "Checks Cascade tool paths and work scope; not an OS sandbox." {
    properties {
        "cascade.semanticId" "element.code.task.guard"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/guard.py"
        "cascade.sourceSymbol" "task_tool_guard"
    }
}

code_task_runtime = element "task: run_swe_turn" "Function" "Builds bounded provider turns and MCP tools. Provider permissions govern native tools." {
    properties {
        "cascade.semanticId" "element.code.task.runtime"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/swe_turn.py"
        "cascade.sourceSymbol" "run_swe_turn"
    }
}

code_task_provider = element "task: build_codex_argv" "Provider adapter" "SWE uses workspace-write unless yolo bypasses sandboxing; other providers differ." {
    properties {
        "cascade.semanticId" "element.code.task.provider"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/agent/codex_cli.py"
        "cascade.sourceSymbol" "build_codex_argv"
    }
}

code_task_rel_43 = code_task_graph -> code_task_state "Uses typed state" {
    properties {
        "cascade.semanticId" "relationship.code-task-graph-to-code-task-state"
    }
}

code_task_rel_44 = code_task_graph -> code_task_checkpoint "Compiles with persistent checkpointer" {
    properties {
        "cascade.semanticId" "relationship.code-task-graph-to-code-task-checkpoint"
    }
}

code_task_rel_45 = code_task_graph -> code_task_runtime "Executes role turns sequentially" {
    properties {
        "cascade.semanticId" "relationship.code-task-graph-to-code-task-runtime"
    }
}

code_task_rel_46 = code_task_wiring -> code_task_registry "Registers tools" {
    properties {
        "cascade.semanticId" "relationship.code-task-wiring-to-code-task-registry"
    }
}

code_task_rel_47 = code_task_runtime -> code_task_registry "Exposes scoped tool calls" {
    properties {
        "cascade.semanticId" "relationship.code-task-runtime-to-code-task-registry"
    }
}

code_task_rel_48 = code_task_registry -> code_task_guard "Tool implementations enforce scope" {
    properties {
        "cascade.semanticId" "relationship.code-task-registry-to-code-task-guard"
    }
}

code_task_rel_49 = code_task_runtime -> code_task_provider "Dispatches through selected adapter" {
    properties {
        "cascade.semanticId" "relationship.code-task-runtime-to-code-task-provider"
    }
}

code_teams_epic = element "teams: ensure_epic_graph" "LangGraph factory" "Creates the epic team graph with scoped state and SQLite checkpoints." {
    properties {
        "cascade.semanticId" "element.code.teams.epic"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/epic/graph.py"
        "cascade.sourceSymbol" "ensure_epic_graph"
    }
}

code_teams_feature = element "teams: ensure_feature_graph" "LangGraph factory" "Creates the feature team graph with scoped state and SQLite checkpoints." {
    properties {
        "cascade.semanticId" "element.code.teams.feature"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/feature/graph.py"
        "cascade.sourceSymbol" "ensure_feature_graph"
    }
}

code_teams_task = element "teams: ensure_task_graph" "LangGraph factory" "Creates the task team graph with scoped state and SQLite checkpoints." {
    properties {
        "cascade.semanticId" "element.code.teams.task"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/task/graph.py"
        "cascade.sourceSymbol" "ensure_task_graph"
    }
}

code_teams_skills = element "teams: load_role_skills_context" "Function" "Resolves role defaults and injects skill text into role prompts." {
    properties {
        "cascade.semanticId" "element.code.teams.skills"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/watchdog/role_skills.py"
        "cascade.sourceSymbol" "load_role_skills_context"
    }
}

code_teams_runtime = element "teams: run_planning_role_turn" "Function" "Builds role turns and routes provider execution through scoped tools." {
    properties {
        "cascade.semanticId" "element.code.teams.runtime"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/agent/graph_turn.py"
        "cascade.sourceSymbol" "run_planning_role_turn"
    }
}

code_teams_rel_50 = code_teams_epic -> code_teams_runtime "Executes planning role turns" {
    properties {
        "cascade.semanticId" "relationship.code-teams-epic-to-code-teams-runtime"
    }
}

code_teams_rel_51 = code_teams_feature -> code_teams_runtime "Executes planning role turns" {
    properties {
        "cascade.semanticId" "relationship.code-teams-feature-to-code-teams-runtime"
    }
}

code_teams_rel_52 = code_teams_runtime -> code_teams_skills "Loads current role playbooks" {
    properties {
        "cascade.semanticId" "relationship.code-teams-runtime-to-code-teams-skills"
    }
}

code_teams_swe = element "teams: run_swe_turn" "Function" "Runs bounded implementation turns with supervised validation and delivery." {
    properties {
        "cascade.semanticId" "element.code.teams.swe"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/task/swe_turn.py"
        "cascade.sourceSymbol" "run_swe_turn"
    }
}

code_teams_rel_53 = code_teams_task -> code_teams_swe "Executes SWE invocation" {
    properties {
        "cascade.semanticId" "relationship.code-teams-task-to-code-teams-swe"
    }
}
