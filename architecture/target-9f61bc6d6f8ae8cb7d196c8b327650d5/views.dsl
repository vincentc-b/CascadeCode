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
    exclude epic_team feature_team task_team
    autoLayout lr
}

// Focused implementation boundary; lifecycle and code diagrams are in the
// owning cascade/{epic,feature,task}/DESIGN.md documents.
component supervisor "cascade-team-components" {
    include team_component epic_team feature_team task_team agent_component watchdog_component repository
    autoLayout lr
}
