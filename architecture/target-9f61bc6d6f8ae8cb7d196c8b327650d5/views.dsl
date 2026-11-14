systemLandscape "cascade-landscape" {
    include *
    autoLayout lr
}

systemContext cascade "cascade-context" {
    include *
    autoLayout lr
}

container cascade "cascade-containers" {
    include *
    autoLayout lr
}

component supervisor "cascade-supervisor-components" {
    include *
    autoLayout lr
}

// Focused implementation boundary; lifecycle and code diagrams are in the
// owning cascade/{epic,feature,task}/DESIGN.md documents.
component supervisor "cascade-team-components" {
    include team_component epic_team feature_team task_team agent_component watchdog_component repository
    autoLayout lr
}

custom "cascade-epic-code" {
    title "Epic team — Code"
    properties {
        "cascade.codeComponent" "element.component.epic-team"
    }
    include code_epic_graph code_epic_state code_epic_checkpoint code_epic_wiring code_epic_registry code_epic_guard code_epic_runtime code_epic_provider
    autoLayout lr
}

custom "cascade-feature-code" {
    title "Feature team — Code"
    properties {
        "cascade.codeComponent" "element.component.feature-team"
    }
    include code_feature_graph code_feature_state code_feature_checkpoint code_feature_wiring code_feature_registry code_feature_guard code_feature_runtime code_feature_provider
    autoLayout lr
}

custom "cascade-task-code" {
    title "Task team — Code"
    properties {
        "cascade.codeComponent" "element.component.task-team"
    }
    include code_task_graph code_task_state code_task_checkpoint code_task_wiring code_task_registry code_task_guard code_task_runtime code_task_provider
    autoLayout lr
}

custom "cascade-teams-code" {
    title "Tier teams — Code"
    properties {
        "cascade.codeComponent" "element.component.teams"
    }
    include code_teams_epic code_teams_feature code_teams_task code_teams_skills code_teams_runtime code_teams_swe
    autoLayout lr
}
