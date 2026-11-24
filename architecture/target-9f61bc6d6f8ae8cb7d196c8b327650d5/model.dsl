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

        diagram_review = component "Diagram comparison" "Coordinates module design comparisons, combined architecture diffs, semantic inspection and pinned review refresh." "Python / JavaScript" {
            properties {
                "cascade.semanticId" "element.component.diagram-review"
            }
        }

        war_room_http = component "HTTP and operator identity" "Serves the loopback UI and dispatches API requests with local operator identity checks." "cascade.war_room.server" {
            properties {
                "cascade.semanticId" "element.component.war-room-http"
            }
        }

        architecture_browser = component "Architecture browser" "Browses revision-pinned branch diagrams, designs, and source." "cascade.war_room.architecture_routes / JavaScript" {
            properties {
                "cascade.semanticId" "element.component.architecture-browser"
            }
        }

        dashboard = component "Dashboard and audit reads" "Shows work state and reads published health-audit projections." "cascade.war_room" {
            properties {
                "cascade.semanticId" "element.component.dashboard"
            }
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
        workspace_component = component "Workspace" "Resolves exact lifecycle owners, repository roles, and revision-pinned architecture." "cascade.workspace" {
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

    cli = container "Operator CLI" "Starts the workspace and runs repository commands and diagnostics." "Python CLI" {
        properties {
            "cascade.semanticId" "element.container.cli"
        }

            workspace_commands = component "Workspace commands" "Dispatches operator commands for initialization, supervised startup and cancellation." "cascade.cli / cascade.workspace" {
                properties {
                    "cascade.semanticId" "element.component.workspace-commands"
                }
            }

            diagnostics = component "Repository diagnostics" "Runs operator-requested probes, including lifecycle checks in an isolated fixture." "cascade.probe" {
                properties {
                    "cascade.semanticId" "element.component.diagnostics"
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
war_room_calls_supervisor = war_room -> supervisor "Invokes authorized in-process operations" {
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

code_epic_checkpoint = element "epic: get_checkpointer" "Function" "langgraph-checkpoint-sqlite stores one SQLite file per work ID." {
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

code_epic_provider = element "epic: build_codex_argv" "Function" "Planning uses provider-default permissions unless yolo bypasses sandboxing; other providers differ." {
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

code_feature_checkpoint = element "feature: get_checkpointer" "Function" "langgraph-checkpoint-sqlite stores one SQLite file per work ID." {
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

code_feature_provider = element "feature: build_codex_argv" "Function" "Planning uses provider-default permissions unless yolo bypasses sandboxing; other providers differ." {
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

code_task_checkpoint = element "task: get_checkpointer" "Function" "langgraph-checkpoint-sqlite stores one SQLite file per work ID." {
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

code_task_provider = element "task: build_codex_argv" "Function" "SWE uses workspace-write unless yolo bypasses sandboxing; other providers differ." {
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

code_teams_epic = element "teams: ensure_epic_graph" "Function" "Creates the epic team graph with scoped state and SQLite checkpoints." {
    properties {
        "cascade.semanticId" "element.code.teams.epic"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/epic/graph.py"
        "cascade.sourceSymbol" "ensure_epic_graph"
    }
}

code_teams_feature = element "teams: ensure_feature_graph" "Function" "Creates the feature team graph with scoped state and SQLite checkpoints." {
    properties {
        "cascade.semanticId" "element.code.teams.feature"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/feature/graph.py"
        "cascade.sourceSymbol" "ensure_feature_graph"
    }
}

code_teams_task = element "teams: ensure_task_graph" "Function" "Creates the task team graph with scoped state and SQLite checkpoints." {
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

code_review_pair = element "Comparison coordinator" "Function" "Owns design directory selection, single-view C4 navigation, selection details and saved viewports." {
    properties {
        "cascade.semanticId" "element.code.code-review-pair"
        "cascade.parent" "element.component.diagram-review"
        "cascade.sourcePath" "cascade/war_room/static/plan_viewer.js"
        "cascade.sourceSymbol" "initPairedC4Review"
    }
}

code_review_navigation = element "Semantic navigation" "Function" "Starts at context, resolves verified detail levels and selections, and keeps landscape optional." {
    properties {
        "cascade.semanticId" "element.code.code-review-navigation"
        "cascade.parent" "element.component.diagram-review"
        "cascade.sourcePath" "cascade/war_room/static/plan_viewer.js"
        "cascade.sourceSymbol" "createPairedNavigation"
    }
}

code_review_svg = element "Semantic SVG viewer" "Function" "Owns viewBox, zoom, pan, Fit and verified SVG target lifecycle." {
    properties {
        "cascade.semanticId" "element.code.code-review-svg"
        "cascade.parent" "element.component.diagram-review"
        "cascade.sourcePath" "cascade/war_room/static/plan_viewer.js"
        "cascade.sourceSymbol" "createSemanticC4Viewer"
    }
}

review_pair_navigation = code_review_pair -> code_review_navigation "Resolves selected semantic identities" {
    properties {
        "cascade.semanticId" "relationship.review-pair-navigation"
    }
}

review_pair_svg = code_review_pair -> code_review_svg "Creates the verified comparison viewer and preserves its viewport" {
    properties {
        "cascade.semanticId" "relationship.review-pair-svg"
    }
}

review_svg_pair = code_review_svg -> code_review_pair "Emits semantic selection and drill events" {
    properties {
        "cascade.semanticId" "relationship.review-svg-pair"
    }
}

code_review_preview = element "Project comparison projection" "Function" "Pins source snapshots and requests a combined presentation artifact." {
    properties {
        "cascade.semanticId" "element.code.code-review-preview"
        "cascade.parent" "element.component.diagram-review"
        "cascade.sourcePath" "cascade/war_room/plan_comparison.py"
        "cascade.sourceSymbol" "draft_diagrams"
    }
}

code_review_union = element "Combined semantic graph" "Function" "Unions targets, retains removals and rewired edges, and serves verified comparison SVGs." {
    properties {
        "cascade.semanticId" "element.code.code-review-union"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/c4_comparison.py"
        "cascade.sourceSymbol" "attach_comparison"
    }
}

code_review_layout = element "Comparison source closure" "Function" "Builds a confined derived Structurizr custom-view source with per-view identity bindings." {
    properties {
        "cascade.semanticId" "element.code.code-review-layout"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/c4_comparison.py"
        "cascade.sourceSymbol" "comparison_source"
    }
}

code_review_scheduler = element "Bounded render scheduler" "Class" "Caches and schedules derived renders without changing review or acceptance authority." {
    properties {
        "cascade.semanticId" "element.code.code-review-scheduler"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/c4_scheduler.py"
        "cascade.sourceSymbol" "C4RenderScheduler"
    }
}

review_pair_preview = code_review_pair -> code_review_preview "Requests committed project comparison" {
    properties {
        "cascade.semanticId" "relationship.review-pair-preview"
    }
}

review_preview_union = code_review_preview -> code_review_union "Supplies authorized pinned semantic projections" {
    properties {
        "cascade.semanticId" "relationship.review-preview-union"
    }
}

review_union_layout = code_review_union -> code_review_layout "Materializes comparison source" {
    properties {
        "cascade.semanticId" "relationship.review-union-layout"
    }
}

review_union_scheduler = code_review_union -> code_review_scheduler "Admits or reuses bounded render" {
    properties {
        "cascade.semanticId" "relationship.review-union-scheduler"
    }
}

review_workspace = diagram_review -> workspace_component "Requests bounded comparison artifacts" {
    properties {
        "cascade.semanticId" "relationship.review-workspace"
    }
}

code_review_documents = element "Committed document comparison" "Function" "Returns all design owners and changed documents from the registered branch base to committed HEAD." {
    properties {
        "cascade.semanticId" "element.code.code-review-documents"
        "cascade.parent" "element.component.diagram-review"
        "cascade.sourcePath" "cascade/war_room/plan_comparison.py"
        "cascade.sourceSymbol" "plan_comparison"
    }
}

code_review_document_body = element "Rendered document comparison" "Function" "Renders current and proposed Markdown with changed-block highlights." {
    properties {
        "cascade.semanticId" "element.code.code-review-document-body"
        "cascade.parent" "element.component.diagram-review"
        "cascade.sourcePath" "cascade/war_room/static/plan_viewer.js"
        "cascade.sourceSymbol" "renderDocumentComparison"
    }
}

code_review_document_changes = element "Document change navigation" "Function" "Moves focus between highlighted blocks with previous/next controls and position indicators." {
    properties {
        "cascade.semanticId" "element.code.code-review-document-changes"
        "cascade.parent" "element.component.diagram-review"
        "cascade.sourcePath" "cascade/war_room/static/plan_viewer.js"
        "cascade.sourceSymbol" "appendChangeNavigation"
    }
}

review_pair_documents = code_review_pair -> code_review_documents "Consumes revision-pinned document data through the document API" {
    properties {
        "cascade.semanticId" "relationship.review-pair-documents"
    }
}

review_pair_document_body = code_review_pair -> code_review_document_body "Renders the selected changed design" {
    properties {
        "cascade.semanticId" "relationship.review-pair-document-body"
    }
}

review_document_changes = code_review_document_body -> code_review_document_changes "Installs navigation after Markdown highlighting" {
    properties {
        "cascade.semanticId" "relationship.review-document-changes"
    }
}

// Runtime and component links used to drill through the container boundaries.

operator_to_cli = operator -> cli "Starts Cascade and runs repository commands" {
    properties {
        "cascade.semanticId" "relationship.operator-to-cli"
    }
}

cli_to_supervisor = cli -> supervisor "Launches and monitors the worker" {
    properties {
        "cascade.semanticId" "relationship.cli-to-supervisor"
    }
}

cli_to_repository = cli -> repository "Initializes, updates and probes the workspace" {
    properties {
        "cascade.semanticId" "relationship.cli-to-repository"
    }
}

war_room_to_repository = war_room -> repository "Reads work, design and audit evidence" {
    properties {
        "cascade.semanticId" "relationship.war-room-to-repository"
    }
}

supervisor_to_forge = supervisor -> forge "Synchronizes work and observes code review" {
    properties {
        "cascade.semanticId" "relationship.supervisor-to-forge"
    }
}

supervisor_to_model_provider = supervisor -> model_provider "Executes configured provider turns" {
    properties {
        "cascade.semanticId" "relationship.supervisor-to-model-provider"
    }
}

supervisor_to_structurizr = supervisor -> structurizr "Runs local validation, export and rendering" {
    properties {
        "cascade.semanticId" "relationship.supervisor-to-structurizr"
    }
}

operator_to_war_room_http = operator -> war_room_http "Opens the loopback UI" {
    properties {
        "cascade.semanticId" "relationship.operator-to-war-room-http"
    }
}

operator_to_workspace_commands = operator -> workspace_commands "Runs local commands" {
    properties {
        "cascade.semanticId" "relationship.operator-to-workspace-commands"
    }
}

architecture_browser_to_supervisor = architecture_browser -> supervisor "Requests pinned architecture evidence" {
    properties {
        "cascade.semanticId" "relationship.architecture-browser-to-supervisor"
    }
}

diagram_review_to_supervisor = diagram_review -> supervisor "Requests review and comparison artifacts" {
    properties {
        "cascade.semanticId" "relationship.diagram-review-to-supervisor"
    }
}

war_room_http_to_architecture_browser = war_room_http -> architecture_browser "Dispatches branch and snapshot requests" {
    properties {
        "cascade.semanticId" "relationship.war-room-http-to-architecture-browser"
    }
}

war_room_http_to_diagram_review = war_room_http -> diagram_review "Dispatches plan comparison requests" {
    properties {
        "cascade.semanticId" "relationship.war-room-http-to-diagram-review"
    }
}

war_room_http_to_dashboard = war_room_http -> dashboard "Serves board and audit routes" {
    properties {
        "cascade.semanticId" "relationship.war-room-http-to-dashboard"
    }
}

architecture_browser_to_workspace_component = architecture_browser -> workspace_component "Resolves and renders pinned branch snapshots" {
    properties {
        "cascade.semanticId" "relationship.architecture-browser-to-workspace-component"
    }
}

dashboard_to_board_component = dashboard -> board_component "Reads canonical work state" {
    properties {
        "cascade.semanticId" "relationship.dashboard-to-board-component"
    }
}

dashboard_to_repository = dashboard -> repository "Reads published audit epochs" {
    properties {
        "cascade.semanticId" "relationship.dashboard-to-repository"
    }
}

board_component_to_repository = board_component -> repository "Reads and validates Markdown lifecycle documents" {
    properties {
        "cascade.semanticId" "relationship.board-component-to-repository"
    }
}

watchdog_component_to_repository = watchdog_component -> repository "Records lifecycle events, recovery evidence and audit epochs" {
    properties {
        "cascade.semanticId" "relationship.watchdog-component-to-repository"
    }
}

boss_component_to_repository = boss_component -> repository "Integrates worktree changes and records closeout" {
    properties {
        "cascade.semanticId" "relationship.boss-component-to-repository"
    }
}

collaboration_component_to_repository = collaboration_component -> repository "Persists comment threads, amendment sidecars and handoffs" {
    properties {
        "cascade.semanticId" "relationship.collaboration-component-to-repository"
    }
}

workspace_component_to_repository = workspace_component -> repository "Resolves worktrees and reads commit-pinned artifacts" {
    properties {
        "cascade.semanticId" "relationship.workspace-component-to-repository"
    }
}

workspace_commands_to_diagnostics = workspace_commands -> diagnostics "Dispatches probe subcommands" {
    properties {
        "cascade.semanticId" "relationship.workspace-commands-to-diagnostics"
    }
}

workspace_commands_to_supervisor = workspace_commands -> supervisor "Starts the supervised worker" {
    properties {
        "cascade.semanticId" "relationship.workspace-commands-to-supervisor"
    }
}

workspace_commands_to_repository = workspace_commands -> repository "Initializes and updates workspace state" {
    properties {
        "cascade.semanticId" "relationship.workspace-commands-to-repository"
    }
}

diagnostics_to_repository = diagnostics -> repository "Examines repository and lifecycle evidence" {
    properties {
        "cascade.semanticId" "relationship.diagnostics-to-repository"
    }
}

// Board — implementation.

code_board_list = element "list_board" "Function" "Scans lifecycle directories and builds the work index." {
    properties {
        "cascade.semanticId" "element.code.board.list"
        "cascade.parent" "element.component.board"
        "cascade.sourcePath" "cascade/board/store.py"
        "cascade.sourceSymbol" "list_board"
    }
}

code_board_index = element "BoardIndex" "Dataclass" "Holds work metadata and duplicates from a directory scan." {
    properties {
        "cascade.semanticId" "element.code.board.index"
        "cascade.parent" "element.component.board"
        "cascade.sourcePath" "cascade/board/types.py"
        "cascade.sourceSymbol" "BoardIndex"
    }
}

code_board_parse = element "parse_doc" "Function" "Parses a Markdown document and its frontmatter." {
    properties {
        "cascade.semanticId" "element.code.board.parse"
        "cascade.parent" "element.component.board"
        "cascade.sourcePath" "cascade/board/parse.py"
        "cascade.sourceSymbol" "parse_doc"
    }
}

code_board_move = element "move_doc" "Function" "Moves a work document between lifecycle columns." {
    properties {
        "cascade.semanticId" "element.code.board.move"
        "cascade.parent" "element.component.board"
        "cascade.sourcePath" "cascade/board/store.py"
        "cascade.sourceSymbol" "move_doc"
    }
}

code_board_validate = element "validate_doc" "Function" "Checks document identity, hierarchy, headings and dependencies." {
    properties {
        "cascade.semanticId" "element.code.board.validate"
        "cascade.parent" "element.component.board"
        "cascade.sourcePath" "cascade/board/validate.py"
        "cascade.sourceSymbol" "validate_doc"
    }
}

board_list_to_parse = code_board_list -> code_board_parse "Reads Markdown metadata during scans" {
    properties {
        "cascade.semanticId" "relationship.board-list-to-parse"
    }
}

board_list_to_index = code_board_list -> code_board_index "Builds" {
    properties {
        "cascade.semanticId" "relationship.code-board-list-to-index"
    }
}

board_move_to_parse = code_board_move -> code_board_parse "Reads the current document" {
    properties {
        "cascade.semanticId" "relationship.code-board-move-to-parse"
    }
}

board_move_to_validate = code_board_move -> code_board_validate "Validates the proposed move before writing" {
    properties {
        "cascade.semanticId" "relationship.code-board-move-to-validate"
    }
}

board_validate_to_index = code_board_validate -> code_board_index "Checks parent and dependency metadata against" {
    properties {
        "cascade.semanticId" "relationship.code-board-validate-to-index"
    }
}


// Agent runtime — implementation.

code_agent_planning = element "run_planning_role_turn" "Function" "Checks turn authorization, prepares scoped inputs and invokes the role runner." {
    properties {
        "cascade.semanticId" "element.code.agent.planning"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/graph_turn.py"
        "cascade.sourceSymbol" "run_planning_role_turn"
    }
}

code_agent_preflight = element "recheck_provider_capability" "Function" "Refreshes provider discovery and records durable capability blockers." {
    properties {
        "cascade.semanticId" "element.code.agent.preflight"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/execution_preflight.py"
        "cascade.sourceSymbol" "recheck_provider_capability"
    }
}

code_agent_runner = element "run_role" "Function" "Dispatches a role turn through its selected provider." {
    properties {
        "cascade.semanticId" "element.code.agent.runner"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/adapter.py"
        "cascade.sourceSymbol" "run_role"
    }
}

code_agent_turn = element "RoleTurn" "Dataclass" "Carries model, working directory, tool and permission settings for a provider invocation." {
    properties {
        "cascade.semanticId" "element.code.agent.turn"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/types.py"
        "cascade.sourceSymbol" "RoleTurn"
    }
}

code_agent_recovery_store = element "RecoveryStore" "Interface" "Defines the read and write contract for persisted role pins." {
    properties {
        "cascade.semanticId" "element.code.agent.recovery-store"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/provider_recovery.py"
        "cascade.sourceSymbol" "RecoveryStore"
    }
}

code_agent_recovery = element "recover_active_provider_pins" "Function" "Validates replacement provider selections and reconciles durable pins." {
    properties {
        "cascade.semanticId" "element.code.agent.recovery"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/provider_recovery.py"
        "cascade.sourceSymbol" "recover_active_provider_pins"
    }
}

agent_planning_to_preflight = code_agent_planning -> code_agent_preflight "Rechecks the pinned selections before running a production turn" {
    properties {
        "cascade.semanticId" "relationship.code-agent-planning-to-preflight"
    }
}

agent_recovery_to_preflight = code_agent_recovery -> code_agent_preflight "Shares the provider capability contract" {
    properties {
        "cascade.semanticId" "relationship.agent-recovery-to-preflight"
    }
}

agent_recovery_to_store = code_agent_recovery -> code_agent_recovery_store "Reads and reconciles selection and checkpoint pins" {
    properties {
        "cascade.semanticId" "relationship.code-agent-recovery-to-store"
    }
}

agent_planning_to_runner = code_agent_planning -> code_agent_runner "Reaches through the scoped planning runner" {
    properties {
        "cascade.semanticId" "relationship.code-agent-planning-to-runner"
    }
}

agent_runner_to_turn = code_agent_runner -> code_agent_turn "Receives" {
    properties {
        "cascade.semanticId" "relationship.code-agent-runner-to-turn"
    }
}


// Watchdog — implementation.

code_watchdog_tick = element "watchdog_tick" "Function" "Checks active work, consumes durable events and advances eligible work." {
    properties {
        "cascade.semanticId" "element.code.watchdog.tick"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/loop.py"
        "cascade.sourceSymbol" "watchdog_tick"
    }
}

code_watchdog_dispatch = element "dispatch_task" "Function" "Checks Task admission before activating and starting work." {
    properties {
        "cascade.semanticId" "element.code.watchdog.dispatch"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/dispatch.py"
        "cascade.sourceSymbol" "dispatch_task"
    }
}

code_watchdog_health = element "sweep_supervisor_health" "Function" "Checks child lifecycle and revalidates recoverable incidents." {
    properties {
        "cascade.semanticId" "element.code.watchdog.health"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/health.py"
        "cascade.sourceSymbol" "sweep_supervisor_health"
    }
}

code_watchdog_audit_lane = element "HealthAuditLane" "Class" "Schedules bounded manual and periodic audit passes." {
    properties {
        "cascade.semanticId" "element.code.watchdog.audit-lane"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/audit_lane.py"
        "cascade.sourceSymbol" "HealthAuditLane"
    }
}

code_watchdog_publish = element "publish_audit_projection" "Function" "Publishes an immutable health audit epoch for dashboard reads." {
    properties {
        "cascade.semanticId" "element.code.watchdog.publish"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/audit_projection.py"
        "cascade.sourceSymbol" "publish_audit_projection"
    }
}

watchdog_tick_to_dispatch = code_watchdog_tick -> code_watchdog_dispatch "Advances eligible Tasks through automation" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-tick-to-dispatch"
    }
}

watchdog_tick_to_health = code_watchdog_tick -> code_watchdog_health "Runs scheduled health checks" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-tick-to-health"
    }
}

watchdog_audit_lane_to_publish = code_watchdog_audit_lane -> code_watchdog_publish "Publishes completed observation evidence" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-audit-lane-to-publish"
    }
}


// Boss — implementation.

code_boss_queue = element "process_boss_queue" "Function" "Handles durable orders and persists the acknowledged queue cursor." {
    properties {
        "cascade.semanticId" "element.code.boss.queue"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/boss/graph.py"
        "cascade.sourceSymbol" "process_boss_queue"
    }
}

code_boss_order = element "process_boss_event" "Function" "Dispatches integration and lifecycle orders." {
    properties {
        "cascade.semanticId" "element.code.boss.order"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/boss/orders.py"
        "cascade.sourceSymbol" "process_boss_event"
    }
}

code_boss_merge = element "merge_task_branch" "Function" "Integrates an approved Task after branch and review checks." {
    properties {
        "cascade.semanticId" "element.code.boss.merge"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/boss/merge.py"
        "cascade.sourceSymbol" "merge_task_branch"
    }
}

code_boss_feature = element "try_complete_feature" "Function" "Evaluates child completion and Feature closeout gates." {
    properties {
        "cascade.semanticId" "element.code.boss.feature"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/boss/rollup.py"
        "cascade.sourceSymbol" "try_complete_feature"
    }
}

code_boss_epic = element "confirm_epic_complete_result" "Function" "Processes operator-confirmed Epic closeout and review state." {
    properties {
        "cascade.semanticId" "element.code.boss.epic"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/boss/epic_complete.py"
        "cascade.sourceSymbol" "confirm_epic_complete_result"
    }
}

code_boss_retry = element "retry_pending_task_merges" "Function" "Resumes deferred Task integration from durable delivery records." {
    properties {
        "cascade.semanticId" "element.code.boss.retry"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/task_rollup.py"
        "cascade.sourceSymbol" "retry_pending_task_merges"
    }
}

boss_queue_to_order = code_boss_queue -> code_boss_order "Dispatches unread orders" {
    properties {
        "cascade.semanticId" "relationship.code-boss-queue-to-order"
    }
}

boss_retry_to_merge = code_boss_retry -> code_boss_merge "Replays pending Task integration" {
    properties {
        "cascade.semanticId" "relationship.code-boss-retry-to-merge"
    }
}

boss_merge_to_feature = code_boss_merge -> code_boss_feature "Successful delivery feeds Feature completion reconciliation" {
    properties {
        "cascade.semanticId" "relationship.code-boss-merge-to-feature"
    }
}

boss_feature_to_epic = code_boss_feature -> code_boss_epic "Supplies child completion evidence" {
    properties {
        "cascade.semanticId" "relationship.code-boss-feature-to-epic"
    }
}


// Comments and amendments — implementation.

code_collaboration_comment = element "comment" "Function" "Records section-addressed feedback in a durable sidecar." {
    properties {
        "cascade.semanticId" "element.code.collaboration.comment"
        "cascade.parent" "element.component.collaboration"
        "cascade.sourcePath" "cascade/comments/store.py"
        "cascade.sourceSymbol" "comment"
    }
}

code_collaboration_route = element "route_feature_comment" "Function" "Routes Feature feedback to the affected Task owner." {
    properties {
        "cascade.semanticId" "element.code.collaboration.route"
        "cascade.parent" "element.component.collaboration"
        "cascade.sourcePath" "cascade/comments/handoffs.py"
        "cascade.sourceSymbol" "route_feature_comment"
    }
}

code_collaboration_gate = element "blocking_threads_for" "Function" "Finds unresolved blocking threads that apply to a work item." {
    properties {
        "cascade.semanticId" "element.code.collaboration.gate"
        "cascade.parent" "element.component.collaboration"
        "cascade.sourcePath" "cascade/comments/gate.py"
        "cascade.sourceSymbol" "blocking_threads_for"
    }
}

code_collaboration_propose = element "propose_epic_amendment" "Function" "Proposes a Feature-to-Epic change to an owned section." {
    properties {
        "cascade.semanticId" "element.code.collaboration.propose"
        "cascade.parent" "element.component.collaboration"
        "cascade.sourcePath" "cascade/feature/amendments.py"
        "cascade.sourceSymbol" "propose_epic_amendment"
    }
}

code_collaboration_sidecar = element "write_sidecar" "Function" "Persists the amendment metadata and proposed diff." {
    properties {
        "cascade.semanticId" "element.code.collaboration.sidecar"
        "cascade.parent" "element.component.collaboration"
        "cascade.sourcePath" "cascade/amendments/store.py"
        "cascade.sourceSymbol" "write_sidecar"
    }
}

code_collaboration_resolve = element "resolve_amendment" "Function" "Applies or declines the recorded amendment under the Epic scope." {
    properties {
        "cascade.semanticId" "element.code.collaboration.resolve"
        "cascade.parent" "element.component.collaboration"
        "cascade.sourcePath" "cascade/epic/amendments.py"
        "cascade.sourceSymbol" "resolve_amendment"
    }
}

collaboration_route_to_comment = code_collaboration_route -> code_collaboration_comment "Routes recorded feedback" {
    properties {
        "cascade.semanticId" "relationship.code-collaboration-route-to-comment"
    }
}

collaboration_gate_to_comment = code_collaboration_gate -> code_collaboration_comment "Evaluates recorded threads" {
    properties {
        "cascade.semanticId" "relationship.code-collaboration-gate-to-comment"
    }
}

collaboration_propose_to_sidecar = code_collaboration_propose -> code_collaboration_sidecar "Stores the proposal" {
    properties {
        "cascade.semanticId" "relationship.code-collaboration-propose-to-sidecar"
    }
}

collaboration_sidecar_to_resolve = code_collaboration_sidecar -> code_collaboration_resolve "Provides evidence for an Epic decision" {
    properties {
        "cascade.semanticId" "relationship.code-collaboration-sidecar-to-resolve"
    }
}


// HTTP and operator identity — implementation.

code_http_serve = element "serve" "Function" "Creates the loopback server and binds its request handler." {
    properties {
        "cascade.semanticId" "element.code.http.serve"
        "cascade.parent" "element.component.war-room-http"
        "cascade.sourcePath" "cascade/war_room/server.py"
        "cascade.sourceSymbol" "serve"
    }
}

code_http_handler = element "WarRoomRequestHandler" "Class" "Dispatches API and page requests." {
    properties {
        "cascade.semanticId" "element.code.http.handler"
        "cascade.parent" "element.component.war-room-http"
        "cascade.sourcePath" "cascade/war_room/server.py"
        "cascade.sourceSymbol" "WarRoomRequestHandler"
    }
}

code_http_identity = element "HumanIdentityVerifier" "Interface" "Defines how the request handler establishes a human principal." {
    properties {
        "cascade.semanticId" "element.code.http.identity"
        "cascade.parent" "element.component.war-room-http"
        "cascade.sourcePath" "cascade/war_room/human_auth.py"
        "cascade.sourceSymbol" "HumanIdentityVerifier"
    }
}

code_http_local = element "LocalHumanIdentityVerifier" "Dataclass" "Verifies the local operator credential." {
    properties {
        "cascade.semanticId" "element.code.http.local"
        "cascade.parent" "element.component.war-room-http"
        "cascade.sourcePath" "cascade/war_room/human_auth.py"
        "cascade.sourceSymbol" "LocalHumanIdentityVerifier"
    }
}

http_serve_to_handler = code_http_serve -> code_http_handler "Installs" {
    properties {
        "cascade.semanticId" "relationship.code-http-serve-to-handler"
    }
}

http_handler_to_identity = code_http_handler -> code_http_identity "Uses for protected requests" {
    properties {
        "cascade.semanticId" "relationship.code-http-handler-to-identity"
    }
}

http_local_to_identity = code_http_local -> code_http_identity "Implements" {
    properties {
        "cascade.semanticId" "relationship.code-http-local-to-identity"
    }
}


// Architecture browser — implementation.

code_browse_controller = element "createController" "Function" "Manages branch selection, drill-down, and previews." {
    properties {
        "cascade.semanticId" "element.code.browse.controller"
        "cascade.parent" "element.component.architecture-browser"
        "cascade.sourcePath" "cascade/war_room/static/architecture_tab.js"
        "cascade.sourceSymbol" "createController"
    }
}

code_browse_snapshot = element "create_snapshot" "Function" "Authorizes the selection and creates a pinned snapshot." {
    properties {
        "cascade.semanticId" "element.code.browse.snapshot"
        "cascade.parent" "element.component.architecture-browser"
        "cascade.sourcePath" "cascade/war_room/architecture_routes.py"
        "cascade.sourceSymbol" "create_snapshot"
    }
}

code_browse_projection = element "snapshot_projection" "Function" "Builds the verified diagram and navigation response." {
    properties {
        "cascade.semanticId" "element.code.browse.projection"
        "cascade.parent" "element.component.architecture-browser"
        "cascade.sourcePath" "cascade/war_room/architecture_routes.py"
        "cascade.sourceSymbol" "snapshot_projection"
    }
}

code_browse_resource = element "resource_bytes" "Function" "Serves approved resources from a pinned revision." {
    properties {
        "cascade.semanticId" "element.code.browse.resource"
        "cascade.parent" "element.component.architecture-browser"
        "cascade.sourcePath" "cascade/war_room/architecture_routes.py"
        "cascade.sourceSymbol" "resource_bytes"
    }
}

browse_controller_to_snapshot = code_browse_controller -> code_browse_snapshot "Pins the selected branch over HTTP" {
    properties {
        "cascade.semanticId" "relationship.code-browse-controller-to-snapshot"
    }
}

browse_controller_to_projection = code_browse_controller -> code_browse_projection "Fetches verified view and target metadata" {
    properties {
        "cascade.semanticId" "relationship.code-browse-controller-to-projection"
    }
}

browse_controller_to_resource = code_browse_controller -> code_browse_resource "Opens pinned design and source resources" {
    properties {
        "cascade.semanticId" "relationship.code-browse-controller-to-resource"
    }
}


// Dashboard and audit reads — implementation.

code_dashboard_router = element "WarRoomRequestHandler.do_GET" "Method" "Routes loopback page and API reads." {
    properties {
        "cascade.semanticId" "element.code.dashboard.router"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/server.py"
        "cascade.sourceSymbol" "WarRoomRequestHandler.do_GET"
    }
}

code_dashboard_render = element "render_war_room_page" "Function" "Renders the main work dashboard shell." {
    properties {
        "cascade.semanticId" "element.code.dashboard.render"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/views.py"
        "cascade.sourceSymbol" "render_war_room_page"
    }
}

code_dashboard_audit = element "handle_get_health_audit_page" "Function" "Validates audit pagination and requests a published epoch." {
    properties {
        "cascade.semanticId" "element.code.dashboard.audit"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/health_routes.py"
        "cascade.sourceSymbol" "handle_get_health_audit_page"
    }
}

code_dashboard_reader = element "read_audit_projection" "Function" "Reads a bounded immutable audit slice." {
    properties {
        "cascade.semanticId" "element.code.dashboard.reader"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/audit_projection_reader.py"
        "cascade.sourceSymbol" "read_audit_projection"
    }
}

dashboard_router_to_render = code_dashboard_router -> code_dashboard_render "Serves the dashboard page" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-router-to-render"
    }
}

dashboard_router_to_audit = code_dashboard_router -> code_dashboard_audit "Dispatches audit page requests" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-router-to-audit"
    }
}

dashboard_audit_to_reader = code_dashboard_audit -> code_dashboard_reader "Reads the requested epoch and section" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-audit-to-reader"
    }
}


// Workspace commands — implementation.

code_cli_main = element "main" "Function" "Parses and dispatches init, up, cancel and probe commands." {
    properties {
        "cascade.semanticId" "element.code.cli.main"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/cli.py"
        "cascade.sourceSymbol" "main"
    }
}

code_cli_up = element "up" "Function" "Prepares the workspace and supervises worker startup." {
    properties {
        "cascade.semanticId" "element.code.cli.up"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/workspace/up.py"
        "cascade.sourceSymbol" "up"
    }
}

code_cli_worker = element "run_worker" "Function" "Starts loopback HTTP, recovery and watchdog execution in the worker." {
    properties {
        "cascade.semanticId" "element.code.cli.worker"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/workspace/worker.py"
        "cascade.sourceSymbol" "run_worker"
    }
}

cli_main_to_up = code_cli_main -> code_cli_up "Dispatches workspace startup" {
    properties {
        "cascade.semanticId" "relationship.code-cli-main-to-up"
    }
}

cli_up_to_worker = code_cli_up -> code_cli_worker "Starts the worker process with a launcher handshake" {
    properties {
        "cascade.semanticId" "relationship.code-cli-up-to-worker"
    }
}


// Repository diagnostics — implementation.

code_probe_command = element "run_probe_command" "Function" "Dispatches preparation and lifecycle diagnostic modes." {
    properties {
        "cascade.semanticId" "element.code.probe.command"
        "cascade.parent" "element.component.diagnostics"
        "cascade.sourcePath" "cascade/probe/cli.py"
        "cascade.sourceSymbol" "run_probe_command"
    }
}

code_probe_workspace = element "probe_workspace" "Function" "Allocates and cleans up a temporary Git workspace for probes." {
    properties {
        "cascade.semanticId" "element.code.probe.workspace"
        "cascade.parent" "element.component.diagnostics"
        "cascade.sourcePath" "cascade/probe/harness.py"
        "cascade.sourceSymbol" "probe_workspace"
    }
}

code_probe_lifecycle = element "run_lifecycle_probe" "Function" "Exercises successful delivery, a stall and recovery inside the fixture." {
    properties {
        "cascade.semanticId" "element.code.probe.lifecycle"
        "cascade.parent" "element.component.diagnostics"
        "cascade.sourcePath" "cascade/probe/lifecycle.py"
        "cascade.sourceSymbol" "run_lifecycle_probe"
    }
}

probe_command_to_workspace = code_probe_command -> code_probe_workspace "Sets up the temporary fixture" {
    properties {
        "cascade.semanticId" "relationship.code-probe-command-to-workspace"
    }
}

probe_command_to_lifecycle = code_probe_command -> code_probe_lifecycle "Runs lifecycle mode inside the fixture" {
    properties {
        "cascade.semanticId" "relationship.code-probe-command-to-lifecycle"
    }
}


// Workspace — implementation.

code_workspace_ownership = element "resolve_design_ownership" "Function" "Resolves the governing design and documentation destination." {
    properties {
        "cascade.semanticId" "element.code.workspace.ownership"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/architecture.py"
        "cascade.sourceSymbol" "resolve_design_ownership"
    }
}

code_workspace_store = element "ArchitectureSnapshotStore" "Class" "Pins architecture context, model source and code revision." {
    properties {
        "cascade.semanticId" "element.code.workspace.store"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/architecture_snapshots.py"
        "cascade.sourceSymbol" "ArchitectureSnapshotStore"
    }
}

code_workspace_closure = element "materialize_c4_source_closure" "Function" "Reads local model inputs from Git at the pinned revision." {
    properties {
        "cascade.semanticId" "element.code.workspace.closure"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/c4_closure.py"
        "cascade.sourceSymbol" "materialize_c4_source_closure"
    }
}

code_workspace_publish = element "publish_architecture_review" "Function" "Publishes scoped review evidence through the bounded renderer." {
    properties {
        "cascade.semanticId" "element.code.workspace.publish"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/architecture_publication.py"
        "cascade.sourceSymbol" "publish_architecture_review"
    }
}

workspace_store_to_closure = code_workspace_store -> code_workspace_closure "Materializes pinned model inputs" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-store-to-closure"
    }
}

workspace_publish_to_closure = code_workspace_publish -> code_workspace_closure "Materializes model inputs for the authorized review" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-publish-to-closure"
    }
}

workspace_store_to_scheduler = code_workspace_store -> code_review_scheduler "Schedules a bounded render" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-store-to-scheduler"
    }
}

workspace_publish_to_scheduler = code_workspace_publish -> code_review_scheduler "Schedules a bounded render" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-publish-to-scheduler"
    }
}

// Epic delivery supervision and recovery.

code_workspace_resolve = element "resolve_doc_worktree" "Function" "Resolve registered document checkout." {
    properties {
        "cascade.semanticId" "element.code.workspace.resolve"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/doc_root.py"
        "cascade.sourceSymbol" "resolve_doc_worktree"
    }
}

code_workspace_mutation_owner = element "resolve_mutation_owner" "Function" "Prove lifecycle write ownership from repository role, lineage, registry identity, and branch." {
    properties {
        "cascade.semanticId" "element.code.workspace.mutation-owner"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "resolve_mutation_owner"
    }
}

code_workspace_doc_owner = element "doc_filesystem_root" "Function" "Route mutation callers through exact owner resolution." {
    properties {
        "cascade.semanticId" "element.code.workspace.doc-owner"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "doc_filesystem_root"
    }
}

code_workspace_board = element "merged_board" "Function" "Project worktree documents and approvals." {
    properties {
        "cascade.semanticId" "element.code.workspace.board"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "merged_board"
    }
}

code_workspace_select = element "_meta_preference" "Function" "Rank document copies for the read projection." {
    properties {
        "cascade.semanticId" "element.code.workspace.select"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "_meta_preference"
    }
}

code_workspace_registry = element "get_integration_worktree" "Function" "Read registered work identity." {
    properties {
        "cascade.semanticId" "element.code.workspace.registry"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "get_integration_worktree"
    }
}

code_workspace_persist = element "terminal_doc_persisted_outside_worktree" "Function" "Check surviving terminal parent document." {
    properties {
        "cascade.semanticId" "element.code.workspace.persist"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "terminal_doc_persisted_outside_worktree"
    }
}

code_workspace_descendant_proof = element "prove_terminal_retirement" "Function" "Enumerates required terminal descendants, persists absent records to the exact parent owner, and requires canonical readback plus delivery provenance." {
    properties {
        "cascade.semanticId" "element.code.workspace.descendant-proof"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "prove_terminal_retirement"
    }
}

code_workspace_retire = element "retire_integration_worktree" "Function" "Remove clean canonical checkout after merge evidence." {
    properties {
        "cascade.semanticId" "element.code.workspace.retire"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "retire_integration_worktree"
    }
}

code_workspace_preflight = element "preflight_lifecycle_merge_target" "Function" "Enforce active target and branch synchronization." {
    properties {
        "cascade.semanticId" "element.code.workspace.preflight"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/branch_synchronization.py"
        "cascade.sourceSymbol" "preflight_lifecycle_merge_target"
    }
}

code_boss_evidence = element "delivery_evidence_is_current" "Function" "Compare the validated source and target pair." {
    properties {
        "cascade.semanticId" "element.code.boss.evidence"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/task_rollup.py"
        "cascade.sourceSymbol" "delivery_evidence_is_current"
    }
}

code_boss_retire = element "_retire_feature_worktree" "Function" "Calls the Workspace descendant proof and preserves refused Feature checkouts for recovery." {
    properties {
        "cascade.semanticId" "element.code.boss.retire"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/boss/rollup.py"
        "cascade.sourceSymbol" "_retire_feature_worktree"
    }
}

code_boss_review = element "ensure_feature_review" "Function" "Publish through review safeguards." {
    properties {
        "cascade.semanticId" "element.code.boss.review"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/review.py"
        "cascade.sourceSymbol" "ensure_feature_review"
    }
}

code_boss_reconcile = element "reconcile_feature_review_completions" "Function" "Reconcile forge acceptance and target closeout." {
    properties {
        "cascade.semanticId" "element.code.boss.reconcile"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/review.py"
        "cascade.sourceSymbol" "reconcile_feature_review_completions"
    }
}

code_boss_lock = element "task_lifecycle_lock" "Function" "Tracking-root cross-process lifecycle lock." {
    properties {
        "cascade.semanticId" "element.code.boss.lock"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/task/lifecycle_lock.py"
        "cascade.sourceSymbol" "task_lifecycle_lock"
    }
}

code_boss_obligation = element "current_feature_obligation" "Function" "Fence closeout and retirement on the current repair, child delivery, review, and integration evidence." {
    properties {
        "cascade.semanticId" "element.code.boss.current-obligation"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/boss/rollup.py"
        "cascade.sourceSymbol" "current_feature_obligation"
    }
}

code_boss_review_generation = element "feature_review_generation" "Function" "Read one immutable Feature review generation while compatibility fields project the current one." {
    properties {
        "cascade.semanticId" "element.code.boss.review-generation"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/review.py"
        "cascade.sourceSymbol" "feature_review_generation"
    }
}

code_watchdog_authority = element "_authorized" "Function" "Bind dispatch event to active path introduction." {
    properties {
        "cascade.semanticId" "element.code.watchdog.authority"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/loop.py"
        "cascade.sourceSymbol" "_authorized"
    }
}

code_watchdog_recover = element "dispatch_audit_recovery" "Function" "Bound observation admission and execution." {
    properties {
        "cascade.semanticId" "element.code.watchdog.recover"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/audit_recovery.py"
        "cascade.sourceSymbol" "dispatch_audit_recovery"
    }
}

code_watchdog_capability = element "CapabilityRegistry" "Class" "Resolve supported operation and accountable owner." {
    properties {
        "cascade.semanticId" "element.code.watchdog.capability"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/capabilities.py"
        "cascade.sourceSymbol" "CapabilityRegistry"
    }
}

code_watchdog_reservation = element "reserve_after_recheck" "Function" "Reserve a freshly rechecked incident generation." {
    properties {
        "cascade.semanticId" "element.code.watchdog.reservation"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/reservations.py"
        "cascade.sourceSymbol" "reserve_after_recheck"
    }
}

code_watchdog_claim = element "accept_claim" "Function" "Accept exact durable execution claim." {
    properties {
        "cascade.semanticId" "element.code.watchdog.claim"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/reservations.py"
        "cascade.sourceSymbol" "accept_claim"
    }
}

code_watchdog_result = element "record_result" "Function" "Record attempt result without asserting health." {
    properties {
        "cascade.semanticId" "element.code.watchdog.result"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/reservations.py"
        "cascade.sourceSymbol" "record_result"
    }
}

code_feature_mint = element "mint_task" "Function" "Admit scoped child specification under lifecycle lock." {
    properties {
        "cascade.semanticId" "element.code.feature.mint"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/mint.py"
        "cascade.sourceSymbol" "mint_task"
    }
}

code_feature_recover = element "recover_task" "Function" "Recover the existing direct child delivery." {
    properties {
        "cascade.semanticId" "element.code.feature.recover"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/recovery.py"
        "cascade.sourceSymbol" "recover_task"
    }
}

code_feature_repair = element "feature_repair" "Function" "Persist and authorize one exact late-repair generation." {
    properties {
        "cascade.semanticId" "element.code.feature.repair"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/repair.py"
        "cascade.sourceSymbol" "feature_repair"
    }
}

code_feature_reserve = element "reserve_repair_child" "Function" "Persist the idempotent Task identity and rendered-spec digest before child and parent writes." {
    properties {
        "cascade.semanticId" "element.code.feature.reserve-repair-child"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/repair.py"
        "cascade.sourceSymbol" "reserve_repair_child"
    }
}

code_epic_recover = element "recover_feature" "Function" "Expose immediate child supervision." {
    properties {
        "cascade.semanticId" "element.code.epic.recover"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/epic/recovery.py"
        "cascade.sourceSymbol" "recover_feature"
    }
}

code_epic_supervise = element "supervise_child" "Function" "Inspect incidents and wake accountable team." {
    properties {
        "cascade.semanticId" "element.code.epic.supervise"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/team_supervision.py"
        "cascade.sourceSymbol" "supervise_child"
    }
}

code_task_actions = element "resume_action" "Function" "Claim and resume durable attempts." {
    properties {
        "cascade.semanticId" "element.code.task.actions"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "resume_action"
    }
}

code_task_leases = element "execution_lease_is_live" "Function" "Reject reuse while execution owner is live." {
    properties {
        "cascade.semanticId" "element.code.task.leases"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/execution.py"
        "cascade.sourceSymbol" "execution_lease_is_live"
    }
}

code_workspace_resolve_to_registry = code_workspace_resolve -> code_workspace_registry "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-resolve-to-registry"
    }
}

code_workspace_resolve_to_board = code_workspace_resolve -> code_workspace_board "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-resolve-to-board"
    }
}

code_workspace_mutation_owner_to_registry = code_workspace_mutation_owner -> code_workspace_registry "Validates exact identity and branch" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-mutation-owner-to-registry"
    }
}

code_workspace_doc_owner_to_mutation_owner = code_workspace_doc_owner -> code_workspace_mutation_owner "Delegates mutation authority" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-doc-owner-to-mutation-owner"
    }
}

code_workspace_board_to_select = code_workspace_board -> code_workspace_select "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-board-to-select"
    }
}

code_workspace_retire_to_registry = code_workspace_retire -> code_workspace_registry "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-retire-to-registry"
    }
}

code_workspace_retire_to_descendant_proof = code_workspace_retire -> code_workspace_descendant_proof "Requires before removal" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-retire-to-descendant-proof"
    }
}

code_workspace_persist_to_descendant_proof = code_workspace_persist -> code_workspace_descendant_proof "Delegates compatibility check" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-persist-to-descendant-proof"
    }
}

code_workspace_persist_to_registry = code_workspace_persist -> code_workspace_registry "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-persist-to-registry"
    }
}

code_workspace_preflight_to_registry = code_workspace_preflight -> code_workspace_registry "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-preflight-to-registry"
    }
}

code_boss_merge_to_evidence = code_boss_merge -> code_boss_evidence "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-boss-merge-to-evidence"
    }
}

code_boss_merge_to_lock = code_boss_merge -> code_boss_lock "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-boss-merge-to-lock"
    }
}

code_boss_rollup_to_lock = code_boss_feature -> code_boss_lock "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-boss-rollup-to-lock"
    }
}

code_boss_rollup_to_review = code_boss_feature -> code_boss_review "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-boss-rollup-to-review"
    }
}

code_boss_rollup_to_retire = code_boss_feature -> code_boss_retire "Requests closeout cleanup" {
    properties {
        "cascade.semanticId" "relationship.code-boss-rollup-to-retire"
    }
}

code_boss_rollup_to_obligation = code_boss_feature -> code_boss_obligation "Checks current generation" {
    properties {
        "cascade.semanticId" "relationship.code-boss-rollup-to-current-obligation"
    }
}

code_boss_obligation_to_review_generation = code_boss_obligation -> code_boss_review_generation "Reads immutable current evidence" {
    properties {
        "cascade.semanticId" "relationship.code-boss-obligation-to-review-generation"
    }
}

code_boss_reconcile_to_rollup = code_boss_reconcile -> code_boss_feature "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-boss-reconcile-to-rollup"
    }
}

code_watchdog_tick_to_authority = code_watchdog_tick -> code_watchdog_authority "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-tick-to-authority"
    }
}

code_watchdog_recover_to_capability = code_watchdog_recover -> code_watchdog_capability "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-recover-to-capability"
    }
}

code_watchdog_recover_to_reservation = code_watchdog_recover -> code_watchdog_reservation "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-recover-to-reservation"
    }
}

code_watchdog_recover_to_claim = code_watchdog_recover -> code_watchdog_claim "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-recover-to-claim"
    }
}

code_watchdog_recover_to_result = code_watchdog_recover -> code_watchdog_result "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-recover-to-result"
    }
}

code_feature_registry_to_mint = code_feature_registry -> code_feature_mint "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-feature-registry-to-mint"
    }
}

code_feature_mint_to_reserve = code_feature_mint -> code_feature_reserve "Reserves before persistence" {
    properties {
        "cascade.semanticId" "relationship.code-feature-mint-to-reserve-repair-child"
    }
}

code_feature_registry_to_recover = code_feature_registry -> code_feature_recover "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-feature-registry-to-recover"
    }
}

code_feature_registry_to_repair = code_feature_registry -> code_feature_repair "Admits exact repair generations" {
    properties {
        "cascade.semanticId" "relationship.code-feature-registry-to-repair"
    }
}

code_epic_registry_to_recover = code_epic_registry -> code_epic_recover "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-epic-registry-to-recover"
    }
}

code_epic_recover_to_supervise = code_epic_recover -> code_epic_supervise "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-epic-recover-to-supervise"
    }
}

code_task_registry_to_actions = code_task_registry -> code_task_actions "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-task-registry-to-actions"
    }
}

code_task_actions_to_leases = code_task_actions -> code_task_leases "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-task-actions-to-leases"
    }
}

boss_uses_workspace = boss_component -> workspace_component "Checks merge targets and retires worktrees" {
    properties {
        "cascade.semanticId" "relationship.boss-uses-workspace"
    }
}

watchdog_uses_boss = watchdog_component -> boss_component "Retries delivery and reconciles closeout" {
    properties {
        "cascade.semanticId" "relationship.watchdog-uses-boss"
    }
}
