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

code_review_preview = element "Project comparison projection" "Function / type" "Pins source snapshots and requests a combined presentation artifact." {
    properties {
        "cascade.semanticId" "element.code.code-review-preview"
        "cascade.parent" "element.component.diagram-review"
        "cascade.sourcePath" "cascade/war_room/plan_comparison.py"
        "cascade.sourceSymbol" "draft_diagrams"
    }
}

code_review_union = element "Combined semantic graph" "Function / type" "Unions targets, retains removals and rewired edges, and serves verified comparison SVGs." {
    properties {
        "cascade.semanticId" "element.code.code-review-union"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/c4_comparison.py"
        "cascade.sourceSymbol" "attach_comparison"
    }
}

code_review_layout = element "Comparison source closure" "Function / type" "Builds a confined derived Structurizr custom-view source with per-view identity bindings." {
    properties {
        "cascade.semanticId" "element.code.code-review-layout"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/c4_comparison.py"
        "cascade.sourceSymbol" "comparison_source"
    }
}

code_review_scheduler = element "Bounded render scheduler" "Function / type" "Caches and schedules derived renders without changing review or acceptance authority." {
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

code_workspace_resolve = element "resolve_doc_worktree" "Python" "Resolve registered document checkout." {
    properties {
        "cascade.semanticId" "element.code.workspace.resolve"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/doc_root.py"
        "cascade.sourceSymbol" "resolve_doc_worktree"
    }
}

code_workspace_board = element "merged_board" "Python" "Project worktree documents and approvals." {
    properties {
        "cascade.semanticId" "element.code.workspace.board"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "merged_board"
    }
}

code_workspace_select = element "_meta_preference" "Python" "Rank document copies for the read projection." {
    properties {
        "cascade.semanticId" "element.code.workspace.select"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "_meta_preference"
    }
}

code_workspace_registry = element "get_integration_worktree" "Python" "Read registered work identity." {
    properties {
        "cascade.semanticId" "element.code.workspace.registry"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "get_integration_worktree"
    }
}

code_workspace_persist = element "terminal_doc_persisted_outside_worktree" "Python" "Check surviving terminal parent document." {
    properties {
        "cascade.semanticId" "element.code.workspace.persist"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "terminal_doc_persisted_outside_worktree"
    }
}

code_workspace_retire = element "retire_integration_worktree" "Python" "Remove clean canonical checkout after merge evidence." {
    properties {
        "cascade.semanticId" "element.code.workspace.retire"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/integration_worktree.py"
        "cascade.sourceSymbol" "retire_integration_worktree"
    }
}

code_workspace_preflight = element "preflight_lifecycle_merge_target" "Python" "Enforce active target and branch synchronization." {
    properties {
        "cascade.semanticId" "element.code.workspace.preflight"
        "cascade.parent" "element.component.workspace"
        "cascade.sourcePath" "cascade/workspace/branch_synchronization.py"
        "cascade.sourceSymbol" "preflight_lifecycle_merge_target"
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

code_boss_merge = element "merge_task_branch" "Python" "Serialize Task delivery and integration gates." {
    properties {
        "cascade.semanticId" "element.code.boss.merge"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/boss/merge.py"
        "cascade.sourceSymbol" "merge_task_branch"
    }
}

code_boss_rollup = element "try_complete_feature" "Python" "Serialize child rollup and review closeout." {
    properties {
        "cascade.semanticId" "element.code.boss.rollup"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/boss/rollup.py"
        "cascade.sourceSymbol" "try_complete_feature"
    }
}

code_boss_queue = element "retry_pending_task_merges" "Python" "Retry durable validated deliveries." {
    properties {
        "cascade.semanticId" "element.code.boss.queue"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/task_rollup.py"
        "cascade.sourceSymbol" "retry_pending_task_merges"
    }
}

code_boss_evidence = element "delivery_evidence_is_current" "Python" "Compare the validated source and target pair." {
    properties {
        "cascade.semanticId" "element.code.boss.evidence"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/task_rollup.py"
        "cascade.sourceSymbol" "delivery_evidence_is_current"
    }
}

code_boss_review = element "ensure_feature_review" "Python" "Publish through review safeguards." {
    properties {
        "cascade.semanticId" "element.code.boss.review"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/review.py"
        "cascade.sourceSymbol" "ensure_feature_review"
    }
}

code_boss_reconcile = element "reconcile_feature_review_completions" "Python" "Reconcile forge acceptance and target closeout." {
    properties {
        "cascade.semanticId" "element.code.boss.reconcile"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/review.py"
        "cascade.sourceSymbol" "reconcile_feature_review_completions"
    }
}

code_boss_lock = element "task_lifecycle_lock" "Python" "Tracking-root cross-process lifecycle lock." {
    properties {
        "cascade.semanticId" "element.code.boss.lock"
        "cascade.parent" "element.component.boss"
        "cascade.sourcePath" "cascade/task/lifecycle_lock.py"
        "cascade.sourceSymbol" "task_lifecycle_lock"
    }
}

code_boss_queue_to_merge = code_boss_queue -> code_boss_merge "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-boss-queue-to-merge"
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

code_boss_rollup_to_lock = code_boss_rollup -> code_boss_lock "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-boss-rollup-to-lock"
    }
}

code_boss_rollup_to_review = code_boss_rollup -> code_boss_review "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-boss-rollup-to-review"
    }
}

code_boss_reconcile_to_rollup = code_boss_reconcile -> code_boss_rollup "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-boss-reconcile-to-rollup"
    }
}

code_watchdog_tick = element "watchdog_tick" "Python" "Reconcile dead claims and scan lifecycle state." {
    properties {
        "cascade.semanticId" "element.code.watchdog.tick"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/loop.py"
        "cascade.sourceSymbol" "watchdog_tick"
    }
}

code_watchdog_authority = element "_authorized" "Python" "Bind dispatch event to active path introduction." {
    properties {
        "cascade.semanticId" "element.code.watchdog.authority"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/loop.py"
        "cascade.sourceSymbol" "_authorized"
    }
}

code_watchdog_recover = element "dispatch_audit_recovery" "Python" "Bound observation admission and execution." {
    properties {
        "cascade.semanticId" "element.code.watchdog.recover"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/audit_recovery.py"
        "cascade.sourceSymbol" "dispatch_audit_recovery"
    }
}

code_watchdog_capability = element "CapabilityRegistry" "Python" "Resolve supported operation and accountable owner." {
    properties {
        "cascade.semanticId" "element.code.watchdog.capability"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/capabilities.py"
        "cascade.sourceSymbol" "CapabilityRegistry"
    }
}

code_watchdog_reservation = element "reserve_after_recheck" "Python" "Reserve a freshly rechecked incident generation." {
    properties {
        "cascade.semanticId" "element.code.watchdog.reservation"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/reservations.py"
        "cascade.sourceSymbol" "reserve_after_recheck"
    }
}

code_watchdog_claim = element "accept_claim" "Python" "Accept exact durable execution claim." {
    properties {
        "cascade.semanticId" "element.code.watchdog.claim"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/reservations.py"
        "cascade.sourceSymbol" "accept_claim"
    }
}

code_watchdog_result = element "record_result" "Python" "Record attempt result without asserting health." {
    properties {
        "cascade.semanticId" "element.code.watchdog.result"
        "cascade.parent" "element.component.watchdog"
        "cascade.sourcePath" "cascade/watchdog/reservations.py"
        "cascade.sourceSymbol" "record_result"
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

code_feature_mint = element "mint_task" "Python" "Admit scoped child specification under lifecycle lock." {
    properties {
        "cascade.semanticId" "element.code.feature.mint"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/mint.py"
        "cascade.sourceSymbol" "mint_task"
    }
}

code_feature_recover = element "recover_task" "Python" "Recover the existing direct child delivery." {
    properties {
        "cascade.semanticId" "element.code.feature.recover"
        "cascade.parent" "element.component.feature-team"
        "cascade.sourcePath" "cascade/feature/recovery.py"
        "cascade.sourceSymbol" "recover_task"
    }
}

code_feature_registry_to_mint = code_feature_registry -> code_feature_mint "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-feature-registry-to-mint"
    }
}

code_feature_registry_to_recover = code_feature_registry -> code_feature_recover "Uses" {
    properties {
        "cascade.semanticId" "relationship.code-feature-registry-to-recover"
    }
}

code_epic_recover = element "recover_feature" "Python" "Expose immediate child supervision." {
    properties {
        "cascade.semanticId" "element.code.epic.recover"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/epic/recovery.py"
        "cascade.sourceSymbol" "recover_feature"
    }
}

code_epic_supervise = element "supervise_child" "Python" "Inspect incidents and wake accountable team." {
    properties {
        "cascade.semanticId" "element.code.epic.supervise"
        "cascade.parent" "element.component.epic-team"
        "cascade.sourcePath" "cascade/team_supervision.py"
        "cascade.sourceSymbol" "supervise_child"
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

code_task_actions = element "resume_action" "Python" "Claim and resume durable attempts." {
    properties {
        "cascade.semanticId" "element.code.task.actions"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/action_recovery.py"
        "cascade.sourceSymbol" "resume_action"
    }
}

code_task_leases = element "execution_lease_is_live" "Python" "Reject reuse while execution owner is live." {
    properties {
        "cascade.semanticId" "element.code.task.leases"
        "cascade.parent" "element.component.task-team"
        "cascade.sourcePath" "cascade/task/execution.py"
        "cascade.sourceSymbol" "execution_lease_is_live"
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
