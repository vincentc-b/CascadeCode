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

        dashboard = component "Dashboard and audit reads" "Owns the safe recovery-progress entry contract and shows work state, immediate lifecycle-action feedback, routing summaries, team transcripts and published projections." "cascade.war_room" {
            properties {
                "cascade.semanticId" "element.component.dashboard"
                "cascade.designPath" "cascade/war_room/DESIGN.md"
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
                "cascade.designPath" "cascade/agent/DESIGN.md"
                "cascade.semanticId" "element.component.agent"
            }
        }
        team_component = component "Tier teams" "Runs persistent Epic/Feature and bounded Task graphs." "cascade.epic/feature/task" {
            properties {
                "cascade.designPath" "cascade/DESIGN.md"
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
        task_team = component "Task team" "Bounded SWE turns with scoped tools, retained action-transition receipts, and exact executor live identity." "cascade.task.graph" {
            properties {
                "cascade.semanticId" "element.component.task-team"
                "cascade.designPath" "cascade/task/DESIGN.md"
            }
        }
        watchdog_component = component "Watchdog" "Admits ready work, retains generation-bound recovery stages, and materializes bounded current progress." "cascade.watchdog / cascade.recovery_progress" {
            properties {
                "cascade.semanticId" "element.component.watchdog"
                "cascade.designPath" "cascade/watchdog/DESIGN.md"
            }
        }
        boss_component = component "Boss" "Owns rollups, merge gates, and completion." "cascade.boss" {
            properties {
                "cascade.semanticId" "element.component.boss"
            }
        }
        workspace_component = component "Workspace" "Resolves lifecycle owners and repository roles, records process-bound invocation evidence, and owns revision-pinned architecture." "cascade.workspace" {
            properties {
                "cascade.semanticId" "element.component.workspace"
                "cascade.designPath" "cascade/workspace/DESIGN.md"
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
                    "cascade.designPath" "cascade/workspace/DESIGN.md"
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

watchdog_uses_task_budget = watchdog_component -> task_team "Consumes the Task-owned incident operation gate after a distinct observation claim" {
    properties {
        "cascade.semanticId" "relationship.watchdog-uses-task-budget"
    }
}

teams_use_task_budget = team_component -> task_team "Reserves and settles cumulative allowance for each review validator operation" {
    properties {
        "cascade.semanticId" "relationship.teams-use-task-budget"
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

agent_uses_task_budget = agent_component -> task_team "Reserves and settles incident-related provider operations through" {
    properties {
        "cascade.semanticId" "relationship.agent-uses-task-budget"
    }
}

task_persists = task_team -> repository "Persists checkpoints, action transitions and work evidence in" {
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

code_epic_graph = element "epic: ensure_epic_graph" "Function" "Compiles sequential role nodes whose authored replies receive durable IDs before checkpoint persistence." {
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

code_epic_runtime = element "epic: run_planning_role_turn" "Function" "Builds scoped provider turns; incident recovery requires Task-budget admission before launch." {
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

code_feature_graph = element "feature: ensure_feature_graph" "Function" "Compiles sequential role nodes whose authored replies receive durable IDs before checkpoint persistence." {
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

code_feature_runtime = element "feature: run_planning_role_turn" "Function" "Builds scoped provider turns; incident recovery requires Task-budget admission before launch." {
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

code_task_runtime = element "task: run_swe_turn" "Function" "Builds scoped provider turns; incident recovery requires Task-budget admission before launch." {
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

code_teams_epic = element "teams: ensure_epic_graph" "Function" "Creates the Epic graph; role-reply IDs persist with its scoped SQLite checkpoint state." {
    properties {
        "cascade.semanticId" "element.code.teams.epic"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/epic/graph.py"
        "cascade.sourceSymbol" "ensure_epic_graph"
    }
}

code_teams_feature = element "teams: ensure_feature_graph" "Function" "Creates the Feature graph; role-reply IDs persist with its scoped SQLite checkpoint state." {
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

watchdog_component_to_repository = watchdog_component -> repository "Records lifecycle events, retained transition evidence and audit epochs" {
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

code_watchdog_progress_drain = element "drain_recovery_progress" "Function" "Fairly replays at most 100 retained receipts and 100 dirty aliases through one shared one-second lock and SQLite deadline." {
    properties {
        "cascade.semanticId" "element.code.watchdog.progress-drain"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/recovery_progress/publisher.py"
        "cascade.sourceSymbol" "drain_recovery_progress"
    }
}

code_watchdog_progress_publish = element "publish_committed_transition" "Function" "Carries one 250 ms deadline through recovery append, publisher locking, mapping and bounded immutable-page publication." {
    properties {
        "cascade.semanticId" "element.code.watchdog.progress-publish"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/recovery_progress/publisher.py"
        "cascade.sourceSymbol" "publish_committed_transition"
    }
}

code_watchdog_milestone_record = element "record_transcript_milestone" "Function" "Uses one 250 ms deadline to map a committed acknowledgement, refresh ordered entry references and publish dirty aliases." {
    properties {
        "cascade.semanticId" "element.code.watchdog.milestone-record"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/recovery_progress/publisher.py"
        "cascade.sourceSymbol" "record_transcript_milestone"
    }
}

code_watchdog_milestone_upsert = element "_record_transcript_milestone" "Function" "Fences current source routing through publisher commit within the caller's remaining deadline and rejects immutable identity conflicts." {
    properties {
        "cascade.semanticId" "element.code.watchdog.milestone-upsert"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/recovery_progress/publisher.py"
        "cascade.sourceSymbol" "_record_transcript_milestone"
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

watchdog_tick_to_progress_drain = code_watchdog_tick -> code_watchdog_progress_drain "Drains committed progress before slow watchdog work" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-tick-to-progress-drain"
    }
}

watchdog_progress_drain_to_publish = code_watchdog_progress_drain -> code_watchdog_progress_publish "Publishes each bounded dirty owner batch" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-progress-drain-to-publish"
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

code_dashboard_progress_contract = element "_derive_entry" "Function" "Defines the versioned safe recovery states, ordering priority, freshness and sanitized presentation fields materialized for Dashboard consumers." {
    properties {
        "cascade.semanticId" "element.code.dashboard.progress-contract"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/recovery_progress/publisher.py"
        "cascade.sourceSymbol" "_derive_entry"
    }
}

code_dashboard_progress_ui = element "loadCurrentRecoveryProgress" "Function" "Reads and renders revision-bound safe recovery entries beside Historical while refusing stale graph or revision responses." {
    properties {
        "cascade.semanticId" "element.code.dashboard.progress-ui"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/static/war_room.js"
        "cascade.sourceSymbol" "loadCurrentRecoveryProgress"
    }
}

code_dashboard_transcript_ui = element "pollChatSidecar" "Function" "Polls incarnation-bound Historical pages and current progress together while merging incremental messages by durable identity without mixing history." {
    properties {
        "cascade.semanticId" "element.code.dashboard.transcript-ui"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/static/war_room.js"
        "cascade.sourceSymbol" "pollChatSidecar"
    }
}

code_dashboard_lifecycle_ui = element "lifecycleActionButton" "Function" "Shows pending and acknowledged Epic actions and row-local refusal reasons across row replacements; waits for canonical board confirmation." {
    properties {
        "cascade.semanticId" "element.code.dashboard.lifecycle-ui"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/static/war_room.js"
        "cascade.sourceSymbol" "lifecycleActionButton"
    }
}

code_dashboard_board_refresh = element "loadBoardView" "Function" "Shares reads, fetches after writes, and defers row replacement during a button press." {
    properties {
        "cascade.semanticId" "element.code.dashboard.board-refresh"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/static/war_room.js"
        "cascade.sourceSymbol" "loadBoardView"
    }
}

code_dashboard_plan_approval = element "initEpicPlanReadinessChrome" "Function" "Shows approval pending or confirmed, preserves exact review context and checks durable approval after an ambiguous response." {
    properties {
        "cascade.semanticId" "element.code.dashboard.plan-approval"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/static/plan_viewer.js"
        "cascade.sourceSymbol" "initEpicPlanReadinessChrome"
    }
}

code_dashboard_post = element "WarRoomRequestHandler.do_POST" "Method" "Routes operator lifecycle writes to canonical services with extended connection deadlines for activation and approval." {
    properties {
        "cascade.semanticId" "element.code.dashboard.post"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/server.py"
        "cascade.sourceSymbol" "WarRoomRequestHandler.do_POST"
    }
}

dashboard_lifecycle_to_post = code_dashboard_lifecycle_ui -> code_dashboard_post "Submits one explicit action with a lifecycle-write deadline" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-lifecycle-to-post"
    }
}

dashboard_lifecycle_to_board_refresh = code_dashboard_lifecycle_ui -> code_dashboard_board_refresh "Reconciles result with canonical board without waiting for optional panels" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-lifecycle-to-board-refresh"
    }
}

dashboard_board_refresh_to_router = code_dashboard_board_refresh -> code_dashboard_router "Reads fresh lifecycle projections" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-board-refresh-to-router"
    }
}

dashboard_plan_approval_to_post = code_dashboard_plan_approval -> code_dashboard_post "Submits exact reviewed plan approval" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-plan-approval-to-post"
    }
}

dashboard_plan_approval_to_router = code_dashboard_plan_approval -> code_dashboard_router "Checks canonical approval and readiness after a refused or ambiguous write" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-plan-approval-to-router"
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

code_workspace_create = element "create_integration_worktree" "Function" "Creates and prepares an integration checkout before publishing its registration and switching Epic or Feature transcript ownership inside its graph fence." {
    properties {
        "cascade.semanticId" "element.code.workspace.create"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "create_integration_worktree"
    }
}

code_watchdog_activate_epic = element "_activate_epic" "Function" "Rechecks human admission and reviewed base, provisions or safely resumes an unstarted Epic checkout, then records activation." {
    properties {
        "cascade.semanticId" "element.code.watchdog.activate-epic"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/dispatch.py"
        "cascade.sourceSymbol" "_activate_epic"
    }
}

code_epic_prepare_checkout = element "prepare_epic_checkout" "Function" "Scrubs inherited child documents from single-repository Epic checkouts before they are exposed to the merged board." {
    properties {
        "cascade.semanticId" "element.code.epic.prepare-checkout"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/epic/activation.py"
        "cascade.sourceSymbol" "prepare_epic_checkout"
    }
}

code_workspace_resume_epic = element "resume_unstarted_epic_worktree" "Function" "Proves canonical clean checkout identity and ancestor-only history, fast-forwards to the approved base and refreshes registration without deleting a branch." {
    properties {
        "cascade.semanticId" "element.code.workspace.resume-epic"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "resume_unstarted_epic_worktree"
    }
}

dashboard_post_to_epic_activation = code_dashboard_post -> code_watchdog_activate_epic "Submits human activation and returns typed outcome" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-post-to-epic-activation"
    }
}

epic_activation_to_workspace_create = code_watchdog_activate_epic -> code_workspace_create "Cuts checkout from the reviewed revision" {
    properties {
        "cascade.semanticId" "relationship.code-epic-activation-to-workspace-create"
    }
}

epic_activation_to_workspace_resume = code_watchdog_activate_epic -> code_workspace_resume_epic "Resumes only when no activation evidence exists" {
    properties {
        "cascade.semanticId" "relationship.code-epic-activation-to-workspace-resume"
    }
}

workspace_create_to_epic_prepare = code_workspace_create -> code_epic_prepare_checkout "Prepares child-document scope before registry publication" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-create-to-epic-prepare"
    }
}

workspace_resume_to_epic_prepare = code_workspace_resume_epic -> code_epic_prepare_checkout "Removes inherited child copies after safe fast-forward" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-resume-to-epic-prepare"
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

code_workspace_descendant_proof = element "prove_terminal_retirement" "Function" "Requires terminal shared Feature delivery evidence before enumerating descendants, persisting absent records, and accepting canonical readback." {
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

code_boss_review = element "ensure_feature_review" "Function" "Refresh an admitted scoped repair on the same open review; terminal or changed review identity fails before push or creation." {
    properties {
        "cascade.semanticId" "element.code.boss.review"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/review.py"
        "cascade.sourceSymbol" "ensure_feature_review"
    }
}

code_boss_review_route = element "_require_repair_review_route" "Function" "Require fresh forge URL and source/target facts before a repair review is reused." {
    properties {
        "cascade.semanticId" "element.code.boss.review-route"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/review.py"
        "cascade.sourceSymbol" "_require_repair_review_route"
    }
}

code_boss_open_review_identity = element "_require_open_review_repair_identity" "Function" "Bind publication to the admitted original review observation or its checkpointed repair action." {
    properties {
        "cascade.semanticId" "element.code.boss.open-review-repair-identity"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/review.py"
        "cascade.sourceSymbol" "_require_open_review_repair_identity"
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

code_boss_obligation = element "current_feature_obligation" "Function" "Fence completion events and retirement on the shared current-generation delivery and intended-target evidence." {
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

code_boss_delivery_view = element "feature_delivery_view" "Function" "Derive read-only Feature delivery phase, retained owner, review identity and next prerequisite from canonical local evidence." {
    properties {
        "cascade.semanticId" "element.code.boss.feature-delivery-view"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/review.py"
        "cascade.sourceSymbol" "feature_delivery_view"
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

code_watchdog_budget_reserve = element "reserve_budgeted_operation" "Function" "Use the accepted Watchdog claim to request a distinct Task-owned bounded operation permit." {
    properties {
        "cascade.semanticId" "element.code.watchdog.budget-reserve"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/reservations.py"
        "cascade.sourceSymbol" "reserve_budgeted_operation"
    }
}

code_watchdog_budget_settle = element "settle_budgeted_operation" "Function" "Settle the distinct Task-owned operation receipt without creating a Watchdog budget." {
    properties {
        "cascade.semanticId" "element.code.watchdog.budget-settle"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/reservations.py"
        "cascade.sourceSymbol" "settle_budgeted_operation"
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

code_watchdog_contract = element "_incident_contract" "Function" "Bind an observed mismatch to the exact Feature owner, capability, and durable mismatch generation." {
    properties {
        "cascade.semanticId" "element.code.watchdog.incident-contract"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/audit_recovery.py"
        "cascade.sourceSymbol" "_incident_contract"
    }
}

code_watchdog_budget_bind = element "_bind_original_incident" "Function" "Anchor parent-lifecycle owner work to the queued action's original Task-owned incident allowance." {
    properties {
        "cascade.semanticId" "element.code.watchdog.budget-bind"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/audit_recovery.py"
        "cascade.sourceSymbol" "_bind_original_incident"
    }
}

code_watchdog_incident_record = element "incident_record" "Function" "Keep original incident identity separate from changing material generation evidence." {
    properties {
        "cascade.semanticId" "element.code.watchdog.incident-record"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/incidents.py"
        "cascade.sourceSymbol" "incident_record"
    }
}

code_watchdog_stage_receipt = element "recovery_stage_receipt" "Function" "Create immutable actor, capability, permitted-input, authority and result evidence for one recovery stage." {
    properties {
        "cascade.semanticId" "element.code.watchdog.stage-receipt"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/incidents.py"
        "cascade.sourceSymbol" "recovery_stage_receipt"
    }
}

code_watchdog_transition_receipt = element "transition_receipt_v1" "Function" "Bind source, generation, work, attempt, claim and monotonic transition sequence into a deterministic safe receipt." {
    properties {
        "cascade.semanticId" "element.code.watchdog.transition-receipt"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/incidents.py"
        "cascade.sourceSymbol" "transition_receipt_v1"
    }
}

code_watchdog_transition_notify = element "_notify_incident_transition" "Function" "Notify the progress publisher with an already committed incident receipt while preserving repair outcome on failure." {
    properties {
        "cascade.semanticId" "element.code.watchdog.transition-notify"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/reservations.py"
        "cascade.sourceSymbol" "_notify_incident_transition"
    }
}

code_watchdog_executor = element "_execute_reservation" "Function" "Invoke the owner adapter only after exact claim acceptance and persist its structured result." {
    properties {
        "cascade.semanticId" "element.code.watchdog.reservation-executor"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/audit_recovery.py"
        "cascade.sourceSymbol" "_execute_reservation"
    }
}

code_watchdog_postcheck = element "reconcile_parent_lifecycle_incident" "Function" "Re-read canonical Task, Feature, repair, review, owner, delivery, lease, retirement and live reviewed-runtime facts for one exact generation." {
    properties {
        "cascade.semanticId" "element.code.watchdog.postcheck"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/incident_postcheck.py"
        "cascade.sourceSymbol" "reconcile_parent_lifecycle_incident"
    }
}

code_watchdog_repair_postcheck = element "reconcile_open_review_repair" "Function" "Observe the original forge review and normalized required checks outside the lifecycle lock, then fence exact current-generation verification before closeout." {
    properties {
        "cascade.semanticId" "element.code.watchdog.repair-postcheck"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/incident_postcheck.py"
        "cascade.sourceSymbol" "reconcile_open_review_repair"
    }
}

code_watchdog_verify = element "verify_incident_postcheck" "Function" "Atomically convert one exact deferred incident to verified history while preserving prior attempts." {
    properties {
        "cascade.semanticId" "element.code.watchdog.verify"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/reservations.py"
        "cascade.sourceSymbol" "verify_incident_postcheck"
    }
}

code_watchdog_incident_projection = element "_incident_projection" "Function" "Serialize bounded typed parent-lifecycle evidence into immutable audit pages." {
    properties {
        "cascade.semanticId" "element.code.watchdog.incident-projection"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/audit_projection.py"
        "cascade.sourceSymbol" "_incident_projection"
    }
}

code_feature_mint = element "mint_task" "Function" "Under the lifecycle lock, join one admitted repair reservation and idempotently repair Task, parent and dispatch event persistence." {
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

code_feature_mismatch_result = element "ParentLifecycleMismatchRecovery" "TypedDict" "Separates selected owner and operation, request, acknowledgement, execution, refusal, and verified postcheck evidence." {
    properties {
        "cascade.semanticId" "element.code.feature.parent-lifecycle-mismatch-recovery"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/recovery.py"
        "cascade.sourceSymbol" "ParentLifecycleMismatchRecovery"
    }
}

code_feature_repair = element "feature_repair" "Function" "Persist, recheck and authorize one exact late-repair generation." {
    properties {
        "cascade.semanticId" "element.code.feature.repair"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/repair.py"
        "cascade.sourceSymbol" "feature_repair"
    }
}

code_feature_open_review_repair = element "admit_open_review_repair" "Function" "Admit a content-addressed parent or authenticated-human request against the existing open Feature review." {
    properties {
        "cascade.semanticId" "element.code.feature.open-review-repair"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/repair.py"
        "cascade.sourceSymbol" "admit_open_review_repair"
    }
}

code_feature_inspect_open_review_repair = element "inspect_open_review_repair" "Function" "Read the canonical live-owner action and refuse a replay whose complete request digest changed under the same request identity." {
    properties {
        "cascade.semanticId" "element.code.feature.inspect-open-review-repair"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/repair.py"
        "cascade.sourceSymbol" "inspect_open_review_repair"
    }
}

code_feature_reserve = element "reserve_repair_child" "Function" "Persist one Task identity, mint-request digest and rendered-spec digest before child and parent writes; changed replay refuses." {
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

code_epic_review_repair_request = element "request_feature_review_repair" "Function" "Authorize one direct-parent or authenticated-human request, admit its exact Feature repair action, and acknowledge wakeup separately from execution." {
    properties {
        "cascade.semanticId" "element.code.epic.review-repair-request"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/team_supervision.py"
        "cascade.sourceSymbol" "request_feature_review_repair"
    }
}

code_epic_mismatch_route = element "_recover_feature_lifecycle_mismatch" "Function" "Verify direct Task ownership and route the exact mismatch generation to Feature recovery." {
    properties {
        "cascade.semanticId" "element.code.epic.parent-lifecycle-mismatch-route"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/team_supervision.py"
        "cascade.sourceSymbol" "_recover_feature_lifecycle_mismatch"
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

code_task_delivery_queue = element "queue_task_merge" "Function" "Persist the validated delivery action, bind its original incident budget, then advertise scheduling." {
    properties {
        "cascade.semanticId" "element.code.task.delivery-queue"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task_rollup.py"
        "cascade.sourceSymbol" "queue_task_merge"
    }
}

code_task_budget_bind = element "bind_incident_budget" "Function" "Anchor canonical actions and material generations to one original incident policy." {
    properties {
        "cascade.semanticId" "element.code.task.incident-budget-bind"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/incident_budget.py"
        "cascade.sourceSymbol" "bind_incident_budget"
    }
}

code_task_budget_read = element "read_incident_budget" "Function" "Project one restart-safe cumulative budget without spending allowance." {
    properties {
        "cascade.semanticId" "element.code.task.incident-budget-read"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/incident_budget.py"
        "cascade.sourceSymbol" "read_incident_budget"
    }
}

code_task_budget_extend = element "extend_incident_budget" "Function" "Append an independently authenticated finite extension within trusted maxima." {
    properties {
        "cascade.semanticId" "element.code.task.incident-budget-extend"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/incident_budget.py"
        "cascade.sourceSymbol" "extend_incident_budget"
    }
}

code_task_budget_exhaust = element "record_incident_budget_exhaustion" "Function" "Persist one stable escalation for exhausted cumulative allowance." {
    properties {
        "cascade.semanticId" "element.code.task.incident-budget-exhaust"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/incident_budget.py"
        "cascade.sourceSymbol" "record_incident_budget_exhaustion"
    }
}

code_task_budget_reserve = element "reserve_incident_operation" "Function" "Atomically verify lineage, policy, material generation, backoff, elapsed deadline, live claim and cumulative remaining allowance." {
    properties {
        "cascade.semanticId" "element.code.task.incident-budget-reserve"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/incident_budget.py"
        "cascade.sourceSymbol" "reserve_incident_operation"
    }
}

code_task_budget_settle = element "settle_incident_operation" "Function" "Idempotently charge observed use or retain an uncertain reservation conservatively." {
    properties {
        "cascade.semanticId" "element.code.task.incident-budget-settle"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/incident_budget.py"
        "cascade.sourceSymbol" "settle_incident_operation"
    }
}

code_task_mismatch = element "ParentLifecycleMismatch" "TypedDict" "Binds one completed-parent refusal to its canonical Feature repair generation." {
    properties {
        "cascade.semanticId" "element.code.task.parent-lifecycle-mismatch"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task_rollup.py"
        "cascade.sourceSymbol" "ParentLifecycleMismatch"
    }
}

code_task_revalidation = element "_request_delivery_revalidation" "Function" "Synchronize a moved Feature base and queue the original Task for an exact replacement final-validation pair." {
    properties {
        "cascade.semanticId" "element.code.task.delivery-revalidation"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task_rollup.py"
        "cascade.sourceSymbol" "_request_delivery_revalidation"
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

code_task_validation = element "swe_run_tests" "Function" "Run scoped pytest and bind a clean committed Task head to its Feature base." {
    properties {
        "cascade.semanticId" "element.code.task.validation"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/git_tools.py"
        "cascade.sourceSymbol" "swe_run_tests"
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

code_boss_review_to_route = code_boss_review -> code_boss_review_route "Checks fresh forge route" {
    properties {
        "cascade.semanticId" "relationship.code-boss-review-to-review-route"
    }
}

code_boss_review_to_open_identity = code_boss_review -> code_boss_open_review_identity "Joins the admitted original review" {
    properties {
        "cascade.semanticId" "relationship.code-boss-review-to-open-review-identity"
    }
}

code_boss_queue_to_task_revalidation = code_boss_queue -> code_task_revalidation "Queues replacement final validation when either head moves" {
    properties {
        "cascade.semanticId" "relationship.code-boss-queue-to-task-revalidation"
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

code_boss_obligation_to_delivery_view = code_boss_obligation -> code_boss_delivery_view "Consumes current delivery and intended-target evidence" {
    properties {
        "cascade.semanticId" "relationship.code-boss-obligation-to-feature-delivery-view"
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

code_watchdog_recover_to_contract = code_watchdog_recover -> code_watchdog_contract "Builds exact admission contract" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-recover-to-incident-contract"
    }
}

code_watchdog_contract_to_capability = code_watchdog_contract -> code_watchdog_capability "Selects owner-scoped capability" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-incident-contract-to-capability"
    }
}

code_watchdog_recover_to_executor = code_watchdog_recover -> code_watchdog_executor "Executes accepted reservation" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-recover-to-reservation-executor"
    }
}

code_watchdog_executor_to_feature_recover = code_watchdog_executor -> code_feature_recover "Invokes canonical Feature repair adapter after claim acceptance" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-reservation-executor-to-feature-recover"
    }
}

code_watchdog_audit_lane_to_postcheck = code_watchdog_audit_lane -> code_watchdog_postcheck "Reassesses deferred mismatch generations after restart and later sweeps" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-audit-lane-to-postcheck"
    }
}

code_watchdog_postcheck_to_verify = code_watchdog_postcheck -> code_watchdog_verify "Closes only the exact proven generation" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-postcheck-to-verify"
    }
}

code_watchdog_publish_to_incident_projection = code_watchdog_publish -> code_watchdog_incident_projection "Projects bounded typed evidence" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-publish-to-incident-projection"
    }
}

code_feature_registry_to_mint = code_feature_registry -> code_feature_mint "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-feature-registry-to-mint"
    }
}

code_feature_mint_to_reserve = code_feature_mint -> code_feature_reserve "Reserves exact child and content before persistence" {
    properties {
        "cascade.semanticId" "relationship.code-feature-mint-to-reserve-repair-child"
    }
}

code_feature_registry_to_recover = code_feature_registry -> code_feature_recover "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-feature-registry-to-recover"
    }
}

code_feature_recover_to_repair = code_feature_recover -> code_feature_repair "Routes completed-parent mismatch through exact repair generation" {
    properties {
        "cascade.semanticId" "relationship.code-feature-recover-to-repair"
    }
}

code_feature_recover_to_mismatch_result = code_feature_recover -> code_feature_mismatch_result "Returns typed recovery evidence" {
    properties {
        "cascade.semanticId" "relationship.code-feature-recover-to-parent-lifecycle-mismatch-recovery"
    }
}

code_feature_registry_to_repair = code_feature_registry -> code_feature_repair "Admits exact repair generations" {
    properties {
        "cascade.semanticId" "relationship.code-feature-registry-to-repair"
    }
}

code_feature_open_review_to_repair = code_feature_open_review_repair -> code_feature_repair "Uses the shared durable admission and introduction state machine" {
    properties {
        "cascade.semanticId" "relationship.code-feature-open-review-to-repair"
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

code_epic_supervise_to_review_repair_request = code_epic_supervise -> code_epic_review_repair_request "Routes exact open-review requests without requiring a Task mismatch" {
    properties {
        "cascade.semanticId" "relationship.code-epic-supervise-to-review-repair-request"
    }
}

code_epic_review_repair_request_to_feature_admission = code_epic_review_repair_request -> code_feature_open_review_repair "Uses the shared content-addressed admission contract" {
    properties {
        "cascade.semanticId" "relationship.code-epic-review-repair-request-to-feature-admission"
    }
}

code_epic_review_repair_request_to_feature_inspection = code_epic_review_repair_request -> code_feature_inspect_open_review_repair "Joins a live owner only after the canonical request digest still matches" {
    properties {
        "cascade.semanticId" "relationship.code-epic-review-repair-request-to-feature-inspection"
    }
}

code_epic_supervise_to_mismatch_route = code_epic_supervise -> code_epic_mismatch_route "Routes exact completed-parent mismatch" {
    properties {
        "cascade.semanticId" "relationship.code-epic-supervise-to-parent-lifecycle-mismatch-route"
    }
}

code_epic_mismatch_route_to_feature_recover = code_epic_mismatch_route -> code_feature_recover "Calls canonical Feature repair adapter" {
    properties {
        "cascade.semanticId" "relationship.code-epic-parent-lifecycle-mismatch-route-to-feature-recover"
    }
}

code_task_registry_to_actions = code_task_registry -> code_task_actions "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-task-registry-to-actions"
    }
}

code_task_mismatch_to_actions = code_task_mismatch -> code_task_actions "Suppresses unchanged delivery retries on the original action" {
    properties {
        "cascade.semanticId" "relationship.code-task-parent-lifecycle-mismatch-to-actions"
    }
}

code_task_actions_to_leases = code_task_actions -> code_task_leases "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-task-actions-to-leases"
    }
}

code_task_validation_to_actions = code_task_validation -> code_task_actions "Publishes validated delivery to durable action" {
    properties {
        "cascade.semanticId" "relationship.code-task-validation-to-actions"
    }
}

code_task_budget_bind_to_actions = code_task_budget_bind -> code_task_actions "Verifies and annotates the canonical durable action" {
    properties {
        "cascade.semanticId" "relationship.code-task-incident-budget-bind-to-actions"
    }
}

code_task_delivery_queue_to_actions = code_task_delivery_queue -> code_task_actions "Persists the canonical queued delivery before scheduling" {
    properties {
        "cascade.semanticId" "relationship.code-task-delivery-queue-to-actions"
    }
}

code_task_delivery_queue_to_budget_bind = code_task_delivery_queue -> code_task_budget_bind "Binds original allowance before the first merge attempt" {
    properties {
        "cascade.semanticId" "relationship.code-task-delivery-queue-to-budget-bind"
    }
}

code_task_budget_read_to_bind = code_task_budget_read -> code_task_budget_bind "Projects the bound original incident record" {
    properties {
        "cascade.semanticId" "relationship.code-task-incident-budget-read-to-bind"
    }
}

code_task_budget_extend_to_bind = code_task_budget_extend -> code_task_budget_bind "Extends the bound trusted policy" {
    properties {
        "cascade.semanticId" "relationship.code-task-incident-budget-extend-to-bind"
    }
}

code_task_budget_exhaust_to_bind = code_task_budget_exhaust -> code_task_budget_bind "Retains one escalation on the bound policy" {
    properties {
        "cascade.semanticId" "relationship.code-task-incident-budget-exhaust-to-bind"
    }
}

code_task_budget_bind_to_watchdog_incident = code_task_budget_bind -> code_watchdog_incident_record "Verifies material generation and persists original identity" {
    properties {
        "cascade.semanticId" "relationship.code-task-incident-budget-bind-to-watchdog-incident-record"
    }
}

code_watchdog_budget_reserve_to_task_budget_reserve = code_watchdog_budget_reserve -> code_task_budget_reserve "Consumes the Task-owned cumulative gate after a distinct capability claim" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-budget-reserve-to-task-budget-reserve"
    }
}

code_watchdog_budget_settle_to_task_budget_settle = code_watchdog_budget_settle -> code_task_budget_settle "Settles the exact charged receipt" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-budget-settle-to-task-budget-settle"
    }
}

code_task_budget_reserve_to_bind = code_task_budget_reserve -> code_task_budget_bind "Verifies the canonical bound material generation and policy" {
    properties {
        "cascade.semanticId" "relationship.code-task-incident-budget-reserve-to-bind"
    }
}

code_task_budget_settle_to_reserve = code_task_budget_settle -> code_task_budget_reserve "Settles the unique durable reservation identity" {
    properties {
        "cascade.semanticId" "relationship.code-task-incident-budget-settle-to-reserve"
    }
}

code_watchdog_repair_authority = element "repair_event_authorizes" "Function" "Join repair event, request/review/claim bindings, current live action, mutation owner and committed active-document introduction." {
    properties {
        "cascade.semanticId" "element.code.watchdog.repair-authority"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/feature/repair.py"
        "cascade.sourceSymbol" "repair_event_authorizes"
    }
}

code_feature_repair_verify = element "mark_feature_repair_verified" "Function" "Persist only an independently verified receipt naming the exact current action, repair generation and corrected checked source head." {
    properties {
        "cascade.semanticId" "element.code.feature.repair-verify"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/repair.py"
        "cascade.sourceSymbol" "mark_feature_repair_verified"
    }
}

code_watchdog_authority_to_repair = code_watchdog_authority -> code_watchdog_repair_authority "Checks generation-bound Feature repair" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-authority-to-repair-authority"
    }
}

code_boss_feature_to_repair_postcheck = code_boss_feature -> code_watchdog_repair_postcheck "Requests fresh verification before the lifecycle critical section" {
    properties {
        "cascade.semanticId" "relationship.code-boss-feature-to-watchdog-repair-postcheck"
    }
}

code_watchdog_repair_postcheck_to_feature_verify = code_watchdog_repair_postcheck -> code_feature_repair_verify "Fences the unchanged action and evidence digest before marking verified" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-repair-postcheck-to-feature-repair-verify"
    }
}

boss_uses_workspace = boss_component -> workspace_component "Checks merge targets and retires worktrees" {
    properties {
        "cascade.semanticId" "relationship.boss-uses-workspace"
    }
}

workspace_uses_boss_delivery = workspace_component -> boss_component "Consumes shared Feature delivery eligibility for wakeup and retirement" {
    properties {
        "cascade.semanticId" "relationship.workspace-uses-boss-delivery"
    }
}

watchdog_uses_boss = watchdog_component -> boss_component "Retries delivery and reconciles closeout" {
    properties {
        "cascade.semanticId" "relationship.watchdog-uses-boss"
    }
}

code_agent_result = element "RoleResult" "Dataclass" "Text, status, tool effects, recovery report and optional normalized invocation receipt." {
    properties {
        "cascade.semanticId" "element.code.agent.result"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/types.py"
        "cascade.sourceSymbol" "RoleResult"
    }
}

code_agent_receipt = element "ProviderInvocationReceipt" "Dataclass" "Records provider, model, invocation identity, non-invented token evidence, outcome and enforceable bounds." {
    properties {
        "cascade.semanticId" "element.code.agent.invocation-receipt"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/types.py"
        "cascade.sourceSymbol" "ProviderInvocationReceipt"
    }
}

code_agent_provider_admit = element "admit_provider_turn" "Function" "Atomically reserves one paid turn and finite worst-case model runtime before provider dispatch." {
    properties {
        "cascade.semanticId" "element.code.agent.provider-admit"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/provider_metering.py"
        "cascade.sourceSymbol" "admit_provider_turn"
    }
}

code_agent_provider_settle = element "settle_provider_turn" "Function" "Normalizes physical invocation evidence and settles known or conservative use exactly once." {
    properties {
        "cascade.semanticId" "element.code.agent.provider-settle"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/provider_metering.py"
        "cascade.sourceSymbol" "settle_provider_turn"
    }
}

code_agent_scoped = element "_run_sandbox_turn" "Function" "Build scoped tools, collect effects and clean up temporary runtime files." {
    properties {
        "cascade.semanticId" "element.code.agent.scoped"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/planning_turn.py"
        "cascade.sourceSymbol" "_run_sandbox_turn"
    }
}

code_agent_dispatch = element "dispatch_planning_tool" "Function" "Apply role catalog and owning tool guards before dispatch." {
    properties {
        "cascade.semanticId" "element.code.agent.dispatch"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/mcp_wrappers.py"
        "cascade.sourceSymbol" "dispatch_planning_tool"
    }
}

code_agent_codex = element "run_codex_role" "Function" "Check Codex tool-host support and supply per-turn MCP configuration." {
    properties {
        "cascade.semanticId" "element.code.agent.codex"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/codex_cli.py"
        "cascade.sourceSymbol" "run_codex_role"
    }
}

code_agent_process = element "run_subprocess_turn" "Function" "Run the CLI with a timeout and direct-process cleanup." {
    properties {
        "cascade.semanticId" "element.code.agent.process"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/cli_common.py"
        "cascade.sourceSymbol" "run_subprocess_turn"
    }
}

code_agent_report = element "report_provider_recovery" "Function" "Report provider-turn outcome while preserving action and checkpoint identity." {
    properties {
        "cascade.semanticId" "element.code.agent.report"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/recovery_contract.py"
        "cascade.sourceSymbol" "report_provider_recovery"
    }
}

code_agent_cancel = element "cancel_live_turns" "Function" "Cancel registered local asyncio tasks and signal recorded provider PIDs." {
    properties {
        "cascade.semanticId" "element.code.agent.cancel"
        "cascade.parent" "element.component.agent"
        "cascade.sourcePath" "cascade/agent/turn_registry.py"
        "cascade.sourceSymbol" "cancel_live_turns"
    }
}

code_teams_publication = element "publish_team_review_resolution" "Function" "Carry canonical incident, claim and operation identities through cumulative admission and exact-SHA publication." {
    properties {
        "cascade.semanticId" "element.code.teams.publication"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/team_review_recovery.py"
        "cascade.sourceSymbol" "publish_team_review_resolution"
    }
}

code_teams_budget_reserve = element "reserve_review_validation" "Function" "Atomically reserve the validator's approved worst-case runtime before any process spawn, linked to a live provider parent when invoked from that turn." {
    properties {
        "cascade.semanticId" "element.code.teams.budget-reserve"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/review_validation.py"
        "cascade.sourceSymbol" "reserve_review_validation"
    }
}

code_teams_validation_operation = element "ReviewValidationOperation" "Dataclass" "Carry the canonical incident, top-level claim, operation identity and durable permit to the validator." {
    properties {
        "cascade.semanticId" "element.code.teams.validation-operation"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/review_validation.py"
        "cascade.sourceSymbol" "ReviewValidationOperation"
    }
}

code_teams_validation_profile = element "ReviewValidationProfile" "Dataclass" "Bind an exact command and coverage class to its policy owner, approval revision and finite timeout/attempt budget." {
    properties {
        "cascade.semanticId" "element.code.teams.validation-profile"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/review_validation.py"
        "cascade.sourceSymbol" "ReviewValidationProfile"
    }
}

code_teams_validate_publish = element "check_and_publish_review_rebase" "Function" "Validate immutable source then recheck policy, remote heads and authority before leased push." {
    properties {
        "cascade.semanticId" "element.code.teams.validate_publish"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/review_rebase.py"
        "cascade.sourceSymbol" "check_and_publish_review_rebase"
    }
}

code_teams_validator = element "run_review_validation" "Function" "Verify a live permit, run one bounded process group, and settle success, failure, timeout or interruption." {
    properties {
        "cascade.semanticId" "element.code.teams.validator"
        "cascade.parent" "element.component.teams"
        "cascade.sourcePath" "cascade/review_validation.py"
        "cascade.sourceSymbol" "run_review_validation"
    }
}

code_task_generation = element "admit_review_publication_generation" "Function" "Record material publication evidence without granting allowance or growing the attempt bound." {
    properties {
        "cascade.semanticId" "element.code.task.generation"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "admit_review_publication_generation"
    }
}

code_cli_launcher = element "run_launcher_loop" "Function" "Supervise safe-path worker startup, handshake, bounded retries and restart." {
    properties {
        "cascade.semanticId" "element.code.cli.launcher"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/workspace/launcher.py"
        "cascade.sourceSymbol" "run_launcher_loop"
    }
}

code_cli_drain = element "drain_and_shutdown" "Function" "Drain HTTP and agent turns before worker shutdown." {
    properties {
        "cascade.semanticId" "element.code.cli.drain"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/workspace/worker.py"
        "cascade.sourceSymbol" "drain_and_shutdown"
    }
}

code_cli_status = element "_worker_supervisor_status" "Function" "Publish lifecycle state and loaded-worker runtime evidence." {
    properties {
        "cascade.semanticId" "element.code.cli.status"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/workspace/worker.py"
        "cascade.sourceSymbol" "_worker_supervisor_status"
    }
}

code_cli_runtime_authority = element "create_runtime_authority" "Function" "Authenticate a deployment receipt and bind clean accepted/integrated checkouts to installed bytes." {
    properties {
        "cascade.semanticId" "element.code.cli.runtime-authority"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/workspace/runtime_identity.py"
        "cascade.sourceSymbol" "create_runtime_authority"
    }
}

code_cli_loaded_runtime = element "loaded_runtime_identity" "Function" "Report imported repair/delivery module origins and worker process/capability evidence without self-verification." {
    properties {
        "cascade.semanticId" "element.code.cli.loaded-runtime"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/workspace/runtime_identity.py"
        "cascade.sourceSymbol" "loaded_runtime_identity"
    }
}

code_cli_validate_runtime = element "validate_runtime_authority" "Function" "Authenticate authority and reject moved, dirty, stale, unintegrated or byte-mismatched evidence." {
    properties {
        "cascade.semanticId" "element.code.cli.validate-runtime"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/workspace/runtime_identity.py"
        "cascade.sourceSymbol" "validate_runtime_authority"
    }
}

code_cli_host_verify_runtime = element "verify_loaded_runtime_identity" "Function" "Return a typed current/pending/refused verdict after inspecting the live child, import root, module bytes and capability generation." {
    properties {
        "cascade.semanticId" "element.code.cli.host-verify-runtime"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/workspace/runtime_identity.py"
        "cascade.sourceSymbol" "verify_loaded_runtime_identity"
    }
}

code_cli_current_runtime = element "verify_current_loaded_runtime_identity" "Function" "Reinspect a launcher-verified receipt, live process, reviewed/integrated lineage, module bytes and capability generation before closeout." {
    properties {
        "cascade.semanticId" "element.code.cli.current-runtime"
        "cascade.parent" "element.component.workspace-commands"
        "cascade.sourcePath" "cascade/workspace/runtime_identity.py"
        "cascade.sourceSymbol" "verify_current_loaded_runtime_identity"
    }
}

code_agent_scoped_to_code_agent_runner = code_agent_scoped -> code_agent_runner "Invokes with scoped tools" {
    properties {
        "cascade.semanticId" "relationship.code-agent-scoped-to-code-agent-runner"
    }
}

code_agent_scoped_to_code_agent_dispatch = code_agent_scoped -> code_agent_dispatch "Provides guarded tool transport" {
    properties {
        "cascade.semanticId" "relationship.code-agent-scoped-to-code-agent-dispatch"
    }
}

code_agent_runner_to_code_agent_codex = code_agent_runner -> code_agent_codex "Dispatches Codex turns" {
    properties {
        "cascade.semanticId" "relationship.code-agent-runner-to-code-agent-codex"
    }
}

code_agent_codex_to_code_agent_process = code_agent_codex -> code_agent_process "Launches CLI" {
    properties {
        "cascade.semanticId" "relationship.code-agent-codex-to-code-agent-process"
    }
}

code_agent_runner_to_code_agent_report = code_agent_runner -> code_agent_report "Normalizes recovery outcome" {
    properties {
        "cascade.semanticId" "relationship.code-agent-runner-to-code-agent-report"
    }
}

code_agent_runner_to_code_agent_result = code_agent_runner -> code_agent_result "Returns" {
    properties {
        "cascade.semanticId" "relationship.code-agent-runner-to-code-agent-result"
    }
}

code_agent_runner_to_code_agent_provider_admit = code_agent_runner -> code_agent_provider_admit "Requires admission immediately before dispatch" {
    properties {
        "cascade.semanticId" "relationship.code-agent-runner-to-provider-admit"
    }
}

code_agent_runner_to_code_agent_provider_settle = code_agent_runner -> code_agent_provider_settle "Settles success, error, timeout and interruption" {
    properties {
        "cascade.semanticId" "relationship.code-agent-runner-to-provider-settle"
    }
}

code_agent_provider_admit_to_code_task_budget_reserve = code_agent_provider_admit -> code_task_budget_reserve "Consumes the Task-owned incident allowance" {
    properties {
        "cascade.semanticId" "relationship.code-agent-provider-admit-to-task-budget-reserve"
    }
}

code_agent_provider_settle_to_code_task_budget_settle = code_agent_provider_settle -> code_task_budget_settle "Settles the canonical operation receipt" {
    properties {
        "cascade.semanticId" "relationship.code-agent-provider-settle-to-task-budget-settle"
    }
}

code_agent_result_to_code_agent_receipt = code_agent_result -> code_agent_receipt "Carries normalized invocation evidence" {
    properties {
        "cascade.semanticId" "relationship.code-agent-result-to-invocation-receipt"
    }
}

code_agent_report_to_code_agent_result = code_agent_report -> code_agent_result "Populates recovery report" {
    properties {
        "cascade.semanticId" "relationship.code-agent-report-to-code-agent-result"
    }
}

code_agent_cancel_to_code_agent_process = code_agent_cancel -> code_agent_process "Signals the registered provider PID" {
    properties {
        "cascade.semanticId" "relationship.code-agent-cancel-to-code-agent-process"
    }
}

code_teams_publication_to_code_teams_validate_publish = code_teams_publication -> code_teams_validate_publish "Executes admitted publication" {
    properties {
        "cascade.semanticId" "relationship.code-teams-publication-to-code-teams-validate-publish"
    }
}

code_teams_publication_to_code_teams_budget_reserve = code_teams_publication -> code_teams_budget_reserve "Reserves before action execution or validator spawn" {
    properties {
        "cascade.semanticId" "relationship.code-teams-publication-to-code-teams-budget-reserve"
    }
}

code_teams_budget_reserve_to_code_task_budget_reserve = code_teams_budget_reserve -> code_task_budget_reserve "Consumes the Task-owned cumulative gate" {
    properties {
        "cascade.semanticId" "relationship.code-teams-budget-reserve-to-code-task-budget-reserve"
    }
}

code_teams_budget_reserve_to_code_teams_validation_operation = code_teams_budget_reserve -> code_teams_validation_operation "Issues canonical validator permit" {
    properties {
        "cascade.semanticId" "relationship.code-teams-budget-reserve-to-code-teams-validation-operation"
    }
}

code_teams_validation_operation_to_code_teams_validation_profile = code_teams_validation_operation -> code_teams_validation_profile "Carries the approved finite profile" {
    properties {
        "cascade.semanticId" "relationship.code-teams-validation-operation-to-code-teams-validation-profile"
    }
}

code_teams_validate_publish_to_code_teams_validator = code_teams_validate_publish -> code_teams_validator "Runs repository checks" {
    properties {
        "cascade.semanticId" "relationship.code-teams-validate-publish-to-code-teams-validator"
    }
}

code_teams_validator_to_code_teams_validation_operation = code_teams_validator -> code_teams_validation_operation "Verifies the live receipt before spawn" {
    properties {
        "cascade.semanticId" "relationship.code-teams-validator-to-code-teams-validation-operation"
    }
}

code_watchdog_incident_record_to_code_watchdog_stage_receipt = code_watchdog_incident_record -> code_watchdog_stage_receipt "Embeds immutable stage evidence" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-incident-record-to-stage-receipt"
    }
}

code_watchdog_contract_to_code_watchdog_budget_bind = code_watchdog_contract -> code_watchdog_budget_bind "Anchors the original obligation before owner admission" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-incident-contract-to-budget-bind"
    }
}

code_watchdog_budget_bind_to_code_task_budget_bind = code_watchdog_budget_bind -> code_task_budget_bind "Uses the sole Task-owned F1 ledger" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-budget-bind-to-task-budget-bind"
    }
}

code_teams_validator_to_code_task_budget_settle = code_teams_validator -> code_task_budget_settle "Settles observed or conservative process usage" {
    properties {
        "cascade.semanticId" "relationship.code-teams-validator-to-code-task-budget-settle"
    }
}

code_teams_publication_to_code_task_generation = code_teams_publication -> code_task_generation "Checks material generation" {
    properties {
        "cascade.semanticId" "relationship.code-teams-publication-to-code-task-generation"
    }
}

code_task_generation_to_code_task_actions = code_task_generation -> code_task_actions "Admits eligible action resumption" {
    properties {
        "cascade.semanticId" "relationship.code-task-generation-to-code-task-actions"
    }
}

code_cli_up_to_code_cli_launcher = code_cli_up -> code_cli_launcher "Starts supervision" {
    properties {
        "cascade.semanticId" "relationship.code-cli-up-to-code-cli-launcher"
    }
}

code_cli_launcher_to_code_cli_worker = code_cli_launcher -> code_cli_worker "Spawns and restarts worker" {
    properties {
        "cascade.semanticId" "relationship.code-cli-launcher-to-code-cli-worker"
    }
}

code_cli_worker_to_code_cli_drain = code_cli_worker -> code_cli_drain "Drains on exit" {
    properties {
        "cascade.semanticId" "relationship.code-cli-worker-to-code-cli-drain"
    }
}

code_cli_worker_to_code_cli_status = code_cli_worker -> code_cli_status "Publishes lifecycle status" {
    properties {
        "cascade.semanticId" "relationship.code-cli-worker-to-code-cli-status"
    }
}

code_cli_main_to_code_cli_runtime_authority = code_cli_main -> code_cli_runtime_authority "Dispatches reviewed runtime bootstrap" {
    properties {
        "cascade.semanticId" "relationship.code-cli-main-to-runtime-authority"
    }
}

code_cli_launcher_to_code_cli_validate_runtime = code_cli_launcher -> code_cli_validate_runtime "Revalidates authority before spawn" {
    properties {
        "cascade.semanticId" "relationship.code-cli-launcher-to-validate-runtime"
    }
}

code_cli_worker_to_code_cli_loaded_runtime = code_cli_worker -> code_cli_loaded_runtime "Measures imported runtime identity" {
    properties {
        "cascade.semanticId" "relationship.code-cli-worker-to-loaded-runtime"
    }
}

code_cli_loaded_runtime_to_code_cli_status = code_cli_loaded_runtime -> code_cli_status "Supplies process-local readiness evidence" {
    properties {
        "cascade.semanticId" "relationship.code-cli-loaded-runtime-to-status"
    }
}

code_cli_launcher_to_code_cli_host_verify_runtime = code_cli_launcher -> code_cli_host_verify_runtime "Independently verifies the spawned child" {
    properties {
        "cascade.semanticId" "relationship.code-cli-launcher-to-host-verify-runtime"
    }
}

code_cli_loaded_runtime_to_code_cli_host_verify_runtime = code_cli_loaded_runtime -> code_cli_host_verify_runtime "Reports loaded origins and process evidence" {
    properties {
        "cascade.semanticId" "relationship.code-cli-loaded-runtime-to-host-verify-runtime"
    }
}

code_cli_host_verify_runtime_to_code_cli_status = code_cli_host_verify_runtime -> code_cli_status "Publishes host-verified identity" {
    properties {
        "cascade.semanticId" "relationship.code-cli-host-verify-runtime-to-status"
    }
}

code_cli_status_to_code_cli_current_runtime = code_cli_status -> code_cli_current_runtime "Supplies the launcher-verified receipt for fresh inspection" {
    properties {
        "cascade.semanticId" "relationship.code-cli-status-to-current-runtime"
    }
}

code_watchdog_postcheck_to_code_cli_current_runtime = code_watchdog_postcheck -> code_cli_current_runtime "Requires current loaded-runtime evidence before incident closeout" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-postcheck-to-current-runtime"
    }
}

code_cli_drain_to_code_agent_cancel = code_cli_drain -> code_agent_cancel "Cancels live provider turns" {
    properties {
        "cascade.semanticId" "relationship.code-cli-drain-to-code-agent-cancel"
    }
}

code_dashboard_recovery = element "board_recovery_projection" "Function" "Projects the published primary entry into the compatible board summary and additive version metadata." {
    properties {
        "cascade.semanticId" "element.code.dashboard.recovery"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/recovery_progress.py"
        "cascade.sourceSymbol" "board_recovery_projection"
    }
}

code_dashboard_incidents = element "read_recovery_progress" "Function" "Reads revision-bound immutable work pages with no-follow opens and aggregate source, row and response ceilings." {
    properties {
        "cascade.semanticId" "element.code.dashboard.incidents"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/recovery_progress.py"
        "cascade.sourceSymbol" "read_recovery_progress"
    }
}

code_dashboard_chat_get = element "handle_get_chat" "Function" "Returns the bounded latest-window compatibility array with continuation and completeness headers." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.get"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/sidecar_routes.py"
        "cascade.sourceSymbol" "handle_get_chat"
    }
}

code_dashboard_chat_read = element "read_messages" "Function" "Reads authoritative JSONL only for explicit writer-side sync and compatibility helpers, never from GET." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.read"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/chat_store.py"
        "cascade.sourceSymbol" "read_messages"
    }
}

code_dashboard_chat_page = element "read_transcript_page" "Function" "Reads incarnation-bound immutable pages with row, aggregate source and serialized response ceilings." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.page"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/transcript_pages.py"
        "cascade.sourceSymbol" "read_transcript_page"
    }
}

code_dashboard_transcript_get = element "handle_get_transcript" "Function" "Validates versioned page and detail queries and returns typed invalid, restart or pending errors." {
    properties {
        "cascade.semanticId" "element.code.dashboard.transcript.get"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/sidecar_routes.py"
        "cascade.sourceSymbol" "handle_get_transcript"
    }
}

code_dashboard_chat_publish = element "publish_transcript_projection" "Function" "Publishes committed offset rows as content-addressed pages and atomically advances the graph pointer." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.publish"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/transcript_pages.py"
        "cascade.sourceSymbol" "publish_transcript_projection"
    }
}

code_dashboard_chat_detail = element "read_transcript_detail" "Function" "Reads one graph/incarnation/message/digest-bound UTF-8 detail chunk without scanning JSONL." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.detail"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/transcript_pages.py"
        "cascade.sourceSymbol" "read_transcript_detail"
    }
}

code_dashboard_chat_append = element "append_transcript_message" "Function" "Appends an exact JSONL line through a durable intent and commits its unique source/message offset after fsync." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.append"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/chat_store.py"
        "cascade.sourceSymbol" "append_transcript_message"
    }
}

code_dashboard_chat_fence = element "graph_transcript_fence" "Function" "Bounds graph thread and process-fence acquisition by the caller's deadline; an admitted lock-file open remains a filesystem baseline." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.fence"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/chat_store.py"
        "cascade.sourceSymbol" "graph_transcript_fence"
    }
}

code_dashboard_chat_source_fence = element "fenced_transcript_source_acknowledgement" "Function" "Yields complete current source-key routing under the deadline-bound graph fence without schema creation, repair, import or projection work." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.source-fence"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/chat_store.py"
        "cascade.sourceSymbol" "fenced_transcript_source_acknowledgement"
    }
}

code_dashboard_chat_index = element "_connect_index" "Function" "Opens the writer-only SQLite append, rewrite and move intent index, refreshing each schema wait from the remaining caller deadline." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.index"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/chat_store.py"
        "cascade.sourceSymbol" "_connect_index"
    }
}

code_dashboard_chat_existing_index = element "_connect_existing_index" "Function" "Opens only an existing compatible transcript index read-only and refreshes every schema and routing query from the caller's remaining deadline." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.existing-index"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/chat_store.py"
        "cascade.sourceSymbol" "_connect_existing_index"
    }
}

code_dashboard_chat_rewrite = element "_rewrite_messages" "Function" "Journals exact replacement bytes and a retry-stable incarnation, fsyncs JSONL, then rebuilds message and source-key offsets." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.rewrite"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/chat_store.py"
        "cascade.sourceSymbol" "_rewrite_messages"
    }
}

code_dashboard_chat_move = element "move_transcript_room" "Function" "Journals and verifies a durable room copy, then switches routing and installs one retry-stable incarnation under the graph fence." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.move"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/chat_store.py"
        "cascade.sourceSymbol" "move_transcript_room"
    }
}

code_dashboard_chat_resume_move = element "resume_transcript_room_move" "Function" "Verifies the journaled destination after terminal owner removal, completes the retained index transition, and republishes the destination incarnation." {
    properties {
        "cascade.semanticId" "element.code.dashboard.chat.resume-move"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/chat_store.py"
        "cascade.sourceSymbol" "resume_transcript_room_move"
    }
}

code_dashboard_recovery_milestone = element "append_committed_recovery_receipt" "Function" "Routes one safe committed receipt and carries the caller's remaining deadline through append and current fenced acknowledgement." {
    properties {
        "cascade.semanticId" "element.code.dashboard.recovery-milestone"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/recovery_milestones.py"
        "cascade.sourceSymbol" "append_committed_recovery_receipt"
    }
}

code_dashboard_transcript = element "append_planning_turn_to_chat" "Function" "Mirrors sanitized authored messages with checkpoint lineage, ordinal and durable message identity after graph invocation returns." {
    properties {
        "cascade.semanticId" "element.code.dashboard.transcript"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/planning_transcript.py"
        "cascade.sourceSymbol" "append_planning_turn_to_chat"
    }
}

code_dashboard_backfill = element "sync_planning_transcript_to_chat" "Function" "Replays checkpointed role identities on explicit writer sync and labels ambiguous legacy author/body matches." {
    properties {
        "cascade.semanticId" "element.code.dashboard.backfill"
        "cascade.parent" "element.component.dashboard"
        "cascade.sourcePath" "cascade/war_room/planning_transcript.py"
        "cascade.sourceSymbol" "sync_planning_transcript_to_chat"
    }
}

code_task_ack = element "acknowledge_team_recovery" "Function" "Commits matching owner acknowledgements in the action ledger." {
    properties {
        "cascade.semanticId" "element.code.task.ack"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "acknowledge_team_recovery"
    }
}

code_task_claim = element "_claim_resume_attempt" "Function" "Atomically appends an attempt and claim under the lifecycle lock." {
    properties {
        "cascade.semanticId" "element.code.task.claim"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "_claim_resume_attempt"
    }
}

code_task_finalize = element "finalize_attempt" "Function" "Persists attempt outcome, recovery state and claim release." {
    properties {
        "cascade.semanticId" "element.code.task.finalize"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "finalize_attempt"
    }
}

code_task_action_checkpoint = element "record_action_checkpoint" "Function" "Persists an idempotent checkpoint for one action attempt." {
    properties {
        "cascade.semanticId" "element.code.task.action-checkpoint"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "record_action_checkpoint"
    }
}

code_task_transition_receipt = element "_append_action_transition" "Function" "Append a generation and attempt-bound v1 transition receipt inside the authoritative action commit." {
    properties {
        "cascade.semanticId" "element.code.task.transition-receipt"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "_append_action_transition"
    }
}

code_task_execution_start = element "_record_execution_start" "Function" "Commit execution-start evidence after preflight and before entering the long executor." {
    properties {
        "cascade.semanticId" "element.code.task.execution-start"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "_record_execution_start"
    }
}

code_task_transition_notify = element "_notify_transition" "Function" "Best-effort after-lock handoff of a committed action receipt and snapshot." {
    properties {
        "cascade.semanticId" "element.code.task.transition-notify"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "_notify_transition"
    }
}

code_workspace_invoke = element "_invoke_role_turn" "Function" "Invokes the graph and mirrors new planning messages after return." {
    properties {
        "cascade.semanticId" "element.code.workspace.invoke"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/kickoff.py"
        "cascade.sourceSymbol" "_invoke_role_turn"
    }
}

code_workspace_owner_live = element "graph_turn_owner_is_live" "Function" "Observes process-local unfinished queue work or a held graph lock; not attempt execution proof." {
    properties {
        "cascade.semanticId" "element.code.workspace.owner.live"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/kickoff.py"
        "cascade.sourceSymbol" "graph_turn_owner_is_live"
    }
}

code_workspace_queue_kickoff = element "kickoff_graph_queue_event" "Function" "Schedule delivery only when the durable queue is ahead of its checkpoint cursor." {
    properties {
        "cascade.semanticId" "element.code.workspace.queue-kickoff"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/kickoff.py"
        "cascade.sourceSymbol" "kickoff_graph_queue_event"
    }
}

code_epic_review_repair_request_to_owner_live = code_epic_review_repair_request -> code_workspace_owner_live "Defers to a live Feature graph owner" {
    properties {
        "cascade.semanticId" "relationship.code-epic-review-repair-request-to-owner-live"
    }
}

code_epic_review_repair_request_to_queue_kickoff = code_epic_review_repair_request -> code_workspace_queue_kickoff "Schedules the already-durable event after admission" {
    properties {
        "cascade.semanticId" "relationship.code-epic-review-repair-request-to-queue-kickoff"
    }
}

code_workspace_kickoff_live = element "_run_kickoff" "Function" "Brackets only the admitted graph invocation with an ephemeral process-bound token." {
    properties {
        "cascade.semanticId" "element.code.workspace.kickoff-live"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/kickoff.py"
        "cascade.sourceSymbol" "_run_kickoff"
    }
}

code_workspace_live_begin = element "begin_live_observation" "Function" "Registers exact invocation or executor identity with a maximum 30-second validity." {
    properties {
        "cascade.semanticId" "element.code.workspace.live-begin"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/recovery_progress/live.py"
        "cascade.sourceSymbol" "begin_live_observation"
    }
}

code_workspace_live_refresh = element "refresh_live_observation" "Function" "Refreshes only a matching registered token while process identity and claim validity remain current." {
    properties {
        "cascade.semanticId" "element.code.workspace.live-refresh"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/recovery_progress/live.py"
        "cascade.sourceSymbol" "refresh_live_observation"
    }
}

code_task_executor_live_identity = element "_executor_live_identity" "Function" "Projects the durable action generation and exact attempt/claim for executor observation." {
    properties {
        "cascade.semanticId" "element.code.task.executor-live-identity"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "_executor_live_identity"
    }
}

dashboard_incidents_to_dashboard_recovery = code_dashboard_incidents -> code_dashboard_recovery "Projects the exact published primary into board compatibility fields" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-incidents-to-dashboard-recovery"
    }
}

dashboard_router_to_progress_reader = code_dashboard_router -> code_dashboard_incidents "Dispatches bounded recovery progress reads" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-router-to-progress-reader"
    }
}

dashboard_progress_ui_to_router = code_dashboard_progress_ui -> code_dashboard_router "Requests bounded revision-bound recovery pages" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-progress-ui-to-router"
    }
}

dashboard_render_to_progress_ui = code_dashboard_render -> code_dashboard_progress_ui "Serves the persistent current-progress presentation" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-render-to-progress-ui"
    }
}

dashboard_render_to_transcript_ui = code_dashboard_render -> code_dashboard_transcript_ui "Serves the durable Historical transcript presentation" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-render-to-transcript-ui"
    }
}

dashboard_transcript_ui_to_router = code_dashboard_transcript_ui -> code_dashboard_router "Requests bounded versioned page and detail reads" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-transcript-ui-to-router"
    }
}

dashboard_recovery_to_progress_contract = code_dashboard_recovery -> code_dashboard_progress_contract "Shares the safe current presentation vocabulary without treating coarse routing as execution proof" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-recovery-to-progress-contract"
    }
}

dashboard_router_to_dashboard_chat_get = code_dashboard_router -> code_dashboard_chat_get "Dispatches chat reads" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-router-to-dashboard-chat-get"
    }
}

dashboard_router_to_dashboard_transcript_get = code_dashboard_router -> code_dashboard_transcript_get "Dispatches versioned transcript page and detail reads" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-router-to-dashboard-transcript-get"
    }
}

dashboard_chat_get_to_dashboard_chat_page = code_dashboard_chat_get -> code_dashboard_chat_page "Reads the bounded latest transcript window" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-get-to-dashboard-chat-page"
    }
}

dashboard_transcript_get_to_dashboard_chat_page = code_dashboard_transcript_get -> code_dashboard_chat_page "Reads bounded immutable transcript pages" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-transcript-get-to-dashboard-chat-page"
    }
}

dashboard_transcript_get_to_dashboard_chat_detail = code_dashboard_transcript_get -> code_dashboard_chat_detail "Reads one immutable oversized-message chunk" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-transcript-get-to-dashboard-chat-detail"
    }
}

dashboard_chat_append_to_publish = code_dashboard_chat_append -> code_dashboard_chat_publish "Publishes committed append offsets for bounded readers" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-append-to-publish"
    }
}

dashboard_transcript_to_dashboard_chat_append = code_dashboard_transcript -> code_dashboard_chat_append "Appends each presentable message" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-transcript-to-dashboard-chat-append"
    }
}

dashboard_recovery_milestone_to_chat_append = code_dashboard_recovery_milestone -> code_dashboard_chat_append "Appends the receipt-keyed recovery line through the durable graph fence" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-recovery-milestone-to-chat-append"
    }
}

dashboard_recovery_milestone_to_chat_source_fence = code_dashboard_recovery_milestone -> code_dashboard_chat_source_fence "Rereads current durable routing within the same remaining deadline" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-recovery-milestone-to-chat-source-fence"
    }
}

dashboard_recovery_milestone_to_workspace_owner = code_dashboard_recovery_milestone -> code_workspace_doc_owner "Resolves Task receipts to their owning Feature room across registered roots" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-recovery-milestone-to-workspace-owner"
    }
}

task_transition_notify_to_progress_publish = code_task_transition_notify -> code_watchdog_progress_publish "Appends and projects the committed receipt after source-lock release" {
    properties {
        "cascade.semanticId" "relationship.code-task-transition-notify-to-progress-publish"
    }
}

watchdog_transition_notify_to_progress_publish = code_watchdog_transition_notify -> code_watchdog_progress_publish "Appends and projects the committed incident receipt after source-lock release" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-transition-notify-to-progress-publish"
    }
}

watchdog_progress_publish_to_recovery_milestone = code_watchdog_progress_publish -> code_dashboard_recovery_milestone "Commits the transcript event before publishing its reference" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-progress-publish-to-recovery-milestone"
    }
}

watchdog_progress_publish_to_milestone_upsert = code_watchdog_progress_publish -> code_watchdog_milestone_upsert "Persists the durable acknowledgement inside the fast-path transaction" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-progress-publish-to-milestone-upsert"
    }
}

watchdog_progress_drain_to_milestone_upsert = code_watchdog_progress_drain -> code_watchdog_milestone_upsert "Persists each replayed durable acknowledgement" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-progress-drain-to-milestone-upsert"
    }
}

watchdog_milestone_record_to_milestone_upsert = code_watchdog_milestone_record -> code_watchdog_milestone_upsert "Validates current fenced routing before updating the durable mapping" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-milestone-record-to-milestone-upsert"
    }
}

watchdog_milestone_upsert_to_chat_source_fence = code_watchdog_milestone_upsert -> code_dashboard_chat_source_fence "Retains authoritative routing fence through the publisher commit" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-milestone-upsert-to-chat-source-fence"
    }
}

dashboard_chat_source_fence_to_fence = code_dashboard_chat_source_fence -> code_dashboard_chat_fence "Serializes source routing with append, rewrite and room movement" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-source-fence-to-fence"
    }
}

dashboard_chat_source_fence_to_existing_index = code_dashboard_chat_source_fence -> code_dashboard_chat_existing_index "Reads complete intent-free source-key routing without schema initialization" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-source-fence-to-existing-index"
    }
}

dashboard_chat_append_to_fence = code_dashboard_chat_append -> code_dashboard_chat_fence "Fences append and exact-tail repair across processes" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-append-to-fence"
    }
}

dashboard_chat_append_to_index = code_dashboard_chat_append -> code_dashboard_chat_index "Commits intent, uniqueness and byte offsets around JSONL fsync" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-append-to-index"
    }
}

dashboard_chat_rewrite_to_fence = code_dashboard_chat_rewrite -> code_dashboard_chat_fence "Fences rollback and legacy-label rewrites across processes" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-rewrite-to-fence"
    }
}

dashboard_chat_rewrite_to_index = code_dashboard_chat_rewrite -> code_dashboard_chat_index "Persists rewrite intent, advances incarnation and rebuilds durable source-key offsets" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-rewrite-to-index"
    }
}

dashboard_chat_rewrite_to_publish = code_dashboard_chat_rewrite -> code_dashboard_chat_publish "Invalidates the old pointer and republishes the committed replacement incarnation" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-rewrite-to-publish"
    }
}

dashboard_chat_move_to_fence = code_dashboard_chat_move -> code_dashboard_chat_fence "Fences room copy and owner switch" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-move-to-fence"
    }
}

dashboard_chat_move_to_index = code_dashboard_chat_move -> code_dashboard_chat_index "Changes incarnation and rebuilds committed offsets" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-move-to-index"
    }
}

dashboard_chat_move_to_publish = code_dashboard_chat_move -> code_dashboard_chat_publish "Invalidates the moving incarnation and republishes the committed destination" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-move-to-publish"
    }
}

dashboard_chat_resume_move_to_fence = code_dashboard_chat_resume_move -> code_dashboard_chat_fence "Fences terminal move recovery against transcript writers" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-resume-move-to-fence"
    }
}

dashboard_chat_resume_move_to_index = code_dashboard_chat_resume_move -> code_dashboard_chat_index "Completes the retained move intent and rebuilt offsets" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-resume-move-to-index"
    }
}

dashboard_chat_resume_move_to_publish = code_dashboard_chat_resume_move -> code_dashboard_chat_publish "Publishes the recovered destination incarnation" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-chat-resume-move-to-publish"
    }
}

workspace_create_to_dashboard_chat_move = code_workspace_create -> code_dashboard_chat_move "Copies committed room history and publishes its new registered owner" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-create-to-dashboard-chat-move"
    }
}

workspace_retire_to_dashboard_chat_move = code_workspace_retire -> code_dashboard_chat_move "Moves history to the surviving owner while retiring the registered checkout" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-retire-to-dashboard-chat-move"
    }
}

workspace_retire_to_dashboard_chat_resume_move = code_workspace_retire -> code_dashboard_chat_resume_move "Resumes the journaled room move when terminal owner removal already completed" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-retire-to-dashboard-chat-resume-move"
    }
}

dashboard_backfill_to_dashboard_chat_read = code_dashboard_backfill -> code_dashboard_chat_read "Reads existing rows only to identify explicitly ambiguous legacy matches" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-backfill-to-dashboard-chat-read"
    }
}

dashboard_backfill_to_dashboard_chat_append = code_dashboard_backfill -> code_dashboard_chat_append "Replays each stable checkpoint message identity" {
    properties {
        "cascade.semanticId" "relationship.code-dashboard-backfill-to-dashboard-chat-append"
    }
}

workspace_invoke_to_dashboard_transcript = code_workspace_invoke -> code_dashboard_transcript "Mirrors messages after graph return" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-invoke-to-dashboard-transcript"
    }
}

workspace_kickoff_live_to_live_begin = code_workspace_kickoff_live -> code_workspace_live_begin "Registers begin/end around the admitted graph call" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-kickoff-live-to-live-begin"
    }
}

workspace_live_refresh_to_live_begin = code_workspace_live_refresh -> code_workspace_live_begin "Matches the registered token and process generation" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-live-refresh-to-live-begin"
    }
}

task_actions_to_task_claim = code_task_actions -> code_task_claim "Claims before executor entry" {
    properties {
        "cascade.semanticId" "relationship.code-task-actions-to-task-claim"
    }
}

task_actions_to_task_finalize = code_task_actions -> code_task_finalize "Records executor outcome" {
    properties {
        "cascade.semanticId" "relationship.code-task-actions-to-task-finalize"
    }
}

task_actions_to_execution_start = code_task_actions -> code_task_execution_start "Commits start after successful preflight" {
    properties {
        "cascade.semanticId" "relationship.code-task-actions-to-execution-start"
    }
}

task_actions_to_executor_live_identity = code_task_actions -> code_task_executor_live_identity "Projects the exact admitted attempt before executor entry" {
    properties {
        "cascade.semanticId" "relationship.code-task-actions-to-executor-live-identity"
    }
}

task_executor_live_identity_to_live_begin = code_task_executor_live_identity -> code_workspace_live_begin "Registers the process-bound executor token" {
    properties {
        "cascade.semanticId" "relationship.code-task-executor-live-identity-to-workspace-live-begin"
    }
}

task_execution_start_to_transition_receipt = code_task_execution_start -> code_task_transition_receipt "Appends the pre-executor receipt" {
    properties {
        "cascade.semanticId" "relationship.code-task-execution-start-to-transition-receipt"
    }
}

task_transition_receipt_to_notify = code_task_transition_receipt -> code_task_transition_notify "Hands off committed receipt after lock release" {
    properties {
        "cascade.semanticId" "relationship.code-task-transition-receipt-to-notify"
    }
}

watchdog_incident_record_to_transition_receipt = code_watchdog_incident_record -> code_watchdog_transition_receipt "Enriches ordered stages with v1 source identity" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-incident-record-to-transition-receipt"
    }
}

watchdog_result_to_transition_notify = code_watchdog_result -> code_watchdog_transition_notify "Notifies only after the incident replacement commits" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-result-to-transition-notify"
    }
}

// Review observation and graph queue eligibility.

code_workspace_delivery = element "deliver_queue_kickoffs" "Function" "Select active, recovery, or retained nonterminal Feature owners whose queue is ahead of its cursor." {
    properties {
        "cascade.semanticId" "element.code.workspace.delivery"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/kickoff.py"
        "cascade.sourceSymbol" "deliver_queue_kickoffs"
    }
}

code_workspace_resume = element "resume_inflight_graphs" "Function" "Rejoin eligible active, recovery, or retained Feature graphs after restart without waking an idle poll." {
    properties {
        "cascade.semanticId" "element.code.workspace.resume"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/kickoff.py"
        "cascade.sourceSymbol" "resume_inflight_graphs"
    }
}

code_workspace_schedule = element "_schedule_queue_delivery" "Function" "Coalesce delivery into the process-local queue worker under graph ownership." {
    properties {
        "cascade.semanticId" "element.code.workspace.schedule"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/kickoff.py"
        "cascade.sourceSymbol" "_schedule_queue_delivery"
    }
}

code_workspace_delivery_locked = element "_run_queue_delivery_locked" "Function" "Recheck retained-owner eligibility under the graph lock, resume interruptions, and advance idle cursors without a role turn." {
    properties {
        "cascade.semanticId" "element.code.workspace.delivery-locked"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/kickoff.py"
        "cascade.sourceSymbol" "_run_queue_delivery_locked"
    }
}

code_workspace_retained_feature = element "_retained_feature_delivery" "Function" "Read the shared nonterminal delivery phase that retains a completed Feature graph without granting repair authority." {
    properties {
        "cascade.semanticId" "element.code.workspace.retained-feature-delivery"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/kickoff.py"
        "cascade.sourceSymbol" "_retained_feature_delivery"
    }
}

code_watchdog_review_health = element "reconcile_open_review_health" "Function" "Observe tracked reviews and admit conflict resolution; clean mergeability alone currently yields healthy." {
    properties {
        "cascade.semanticId" "element.code.watchdog.review-health"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/review_health.py"
        "cascade.sourceSymbol" "reconcile_open_review_health"
    }
}

code_watchdog_review_snapshot = element "merge_request_snapshot" "Function" "Read forge review state, source revision, branch refs and mergeability through the configured CLI." {
    properties {
        "cascade.semanticId" "element.code.watchdog.review-snapshot"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/tracking.py"
        "cascade.sourceSymbol" "merge_request_snapshot"
    }
}

code_boss_review_pending = element "feature_review_pending" "Function" "Read open review state or the completed-document publication window without forging acceptance." {
    properties {
        "cascade.semanticId" "element.code.boss.review-pending"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/review.py"
        "cascade.sourceSymbol" "feature_review_pending"
    }
}

code_workspace_delivery_to_schedule = code_workspace_delivery -> code_workspace_schedule "Schedules unread queue delivery" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-delivery-to-schedule"
    }
}

code_workspace_delivery_to_retained_feature = code_workspace_delivery -> code_workspace_retained_feature "Includes retained completed Feature owners" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-delivery-to-retained-feature"
    }
}

code_workspace_resume_to_retained_feature = code_workspace_resume -> code_workspace_retained_feature "Rechecks retained ownership during restart" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-resume-to-retained-feature"
    }
}

code_workspace_locked_to_retained_feature = code_workspace_delivery_locked -> code_workspace_retained_feature "Rechecks the same eligibility under the graph lock" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-locked-to-retained-feature"
    }
}

code_workspace_retained_feature_to_delivery_view = code_workspace_retained_feature -> code_boss_delivery_view "Consumes the shared read-only Feature delivery projection" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-retained-feature-to-delivery-view"
    }
}

code_workspace_descendant_proof_to_delivery_view = code_workspace_descendant_proof -> code_boss_delivery_view "Requires terminal current-generation delivery before persistence or removal" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-descendant-proof-to-delivery-view"
    }
}

code_workspace_resume_to_schedule = code_workspace_resume -> code_workspace_schedule "Schedules interrupted or staged input replay" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-resume-to-schedule"
    }
}

code_workspace_schedule_to_locked = code_workspace_schedule -> code_workspace_delivery_locked "Runs the coalesced worker under its graph lock" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-schedule-to-locked"
    }
}

code_workspace_delivery_to_invoke = code_workspace_delivery_locked -> code_workspace_invoke "Stages durable input then invokes an eligible role turn" {
    properties {
        "cascade.semanticId" "relationship.code-workspace-delivery-to-invoke"
    }
}

code_watchdog_health_to_snapshot = code_watchdog_review_health -> code_watchdog_review_snapshot "Reads fresh forge facts before conflict admission" {
    properties {
        "cascade.semanticId" "relationship.code-watchdog-health-to-snapshot"
    }
}

code_boss_feature_to_pending = code_boss_feature -> code_boss_review_pending "Retains pending publication and review obligations" {
    properties {
        "cascade.semanticId" "relationship.code-boss-feature-to-pending"
    }
}
