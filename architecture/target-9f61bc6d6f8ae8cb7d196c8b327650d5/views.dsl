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
    include team_component epic_team feature_team task_team agent_component watchdog_component boss_component workspace_component repository
    autoLayout lr
}

custom "cascade-epic-code" {
    title "Epic team — Code"
    properties {
        "cascade.codeComponent" "element.component.epic-team"
    }
    include code_epic_graph code_epic_state code_epic_checkpoint code_epic_wiring code_epic_registry code_epic_guard code_epic_runtime code_epic_provider
    include code_epic_recover code_epic_supervise code_epic_review_repair_request code_epic_mismatch_route code_epic_prepare_checkout
    autoLayout lr
}

custom "cascade-feature-code" {
    title "Feature team — Code"
    properties {
        "cascade.codeComponent" "element.component.feature-team"
    }
    include code_feature_graph code_feature_state code_feature_checkpoint code_feature_wiring code_feature_registry code_feature_guard code_feature_runtime code_feature_provider
    include code_feature_mint code_feature_recover code_feature_retry code_feature_mismatch_result code_feature_repair code_feature_open_review_repair code_feature_inspect_open_review_repair code_feature_latest_open_review_repair code_feature_reserve code_feature_repair_verify
    autoLayout lr
}

custom "cascade-task-code" {
    title "Task team — Code"
    properties {
        "cascade.codeComponent" "element.component.task-team"
    }
    include code_task_graph code_task_state code_task_checkpoint code_task_wiring code_task_registry code_task_guard code_task_runtime code_task_provider
    include code_task_actions code_task_delivery_queue code_task_mismatch code_task_upstream_review_fence code_task_leases code_task_validation code_task_revalidation
    include code_task_generation
    include code_task_budget_bind code_task_budget_read code_task_budget_extend code_task_budget_exhaust code_task_budget_reserve code_task_budget_settle
    include code_task_ack code_task_claim code_task_finalize code_task_action_checkpoint code_task_transition_receipt code_task_execution_start code_task_transition_notify code_task_executor_live_identity
    autoLayout lr
}

custom "cascade-teams-code" {
    title "Tier teams — Code"
    properties {
        "cascade.codeComponent" "element.component.teams"
    }
    include code_teams_epic code_teams_feature code_teams_task code_teams_skills code_teams_runtime code_teams_swe
    include code_teams_publication code_teams_budget_reserve code_teams_validation_operation code_teams_validation_profile code_teams_validate_publish code_teams_validator
    autoLayout lr
}

component war_room "cascade-war-room-components" {
    title "War Room — components"
    include *
    autoLayout lr
}

custom "cascade-diagram-review-code" {
    title "Diagram comparison — Code"
    properties {
        "cascade.codeComponent" "element.component.diagram-review"
    }
    include code_review_pair code_review_navigation code_review_svg code_review_preview code_review_documents code_review_document_body code_review_document_changes
    autoLayout lr
}

custom "cascade-comparison-render-code" {
    title "Combined comparison rendering — Code"
    properties {
        "cascade.codeComponent" "element.component.workspace"
    }
    include code_review_union code_review_layout code_review_scheduler
    autoLayout lr
}

component cli "cascade-cli-components" {
    include *
    autoLayout lr
}

custom "cascade-board-code" {
    title "Board — Code"
    properties {
        "cascade.codeComponent" "element.component.board"
    }
    include code_board_list code_board_index code_board_parse code_board_move code_board_validate
    autoLayout lr
}

custom "cascade-agent-code" {
    title "Agent runtime — Code"
    properties {
        "cascade.codeComponent" "element.component.agent"
    }
    include code_agent_planning code_agent_preflight code_agent_runner code_agent_turn code_agent_recovery code_agent_recovery_store
    include code_agent_result code_agent_receipt code_agent_provider_admit code_agent_provider_settle code_agent_scoped code_agent_dispatch code_agent_codex code_agent_process code_agent_report code_agent_cancel
    autoLayout lr
}

custom "cascade-watchdog-code" {
    title "Watchdog — Code"
    properties {
        "cascade.codeComponent" "element.component.watchdog"
    }
    include code_watchdog_tick code_watchdog_dispatch code_watchdog_dependency_delivery_gate code_watchdog_feature_dispatch_gate code_watchdog_activate_epic code_watchdog_health code_watchdog_audit_lane code_watchdog_publish code_watchdog_progress_drain code_watchdog_progress_publish code_watchdog_milestone_record code_watchdog_milestone_upsert
    include code_watchdog_authority code_watchdog_repair_authority code_watchdog_recover code_watchdog_contract code_watchdog_budget_bind code_watchdog_incident_record code_watchdog_stage_receipt code_watchdog_transition_receipt code_watchdog_transition_notify code_watchdog_executor code_watchdog_capability code_watchdog_reservation code_watchdog_budget_reserve code_watchdog_budget_settle code_watchdog_claim code_watchdog_result code_watchdog_postcheck code_watchdog_repair_postcheck code_watchdog_required_checks code_watchdog_verify code_watchdog_incident_projection
    include code_watchdog_review_health code_watchdog_actionable_review code_watchdog_review_snapshot code_watchdog_review_evidence_health code_watchdog_review_evidence_record
    autoLayout lr
}

custom "cascade-boss-code" {
    title "Boss — Code"
    properties {
        "cascade.codeComponent" "element.component.boss"
    }
    include code_boss_queue code_boss_order code_boss_retry code_boss_merge code_boss_feature code_boss_epic
    include code_boss_evidence code_boss_retire code_boss_review code_boss_review_route code_boss_open_review_identity code_boss_reconcile code_boss_lock code_boss_obligation code_boss_repair_postcheck_gate code_boss_delivery_view code_boss_delivery_execution_predicate code_boss_dependency_delivery_gate
    include code_boss_review_generation code_boss_review_pending
    autoLayout lr
}

custom "cascade-collaboration-code" {
    title "Comments and amendments — Code"
    properties {
        "cascade.codeComponent" "element.component.collaboration"
    }
    include code_collaboration_comment code_collaboration_route code_collaboration_gate code_collaboration_propose code_collaboration_sidecar code_collaboration_resolve
    autoLayout lr
}

custom "cascade-war-room-http-code" {
    title "HTTP and operator identity — Code"
    properties {
        "cascade.codeComponent" "element.component.war-room-http"
    }
    include code_http_serve code_http_handler code_http_identity code_http_local code_http_review_repair
    autoLayout lr
}

custom "cascade-architecture-browser-code" {
    title "Architecture browser — Code"
    properties {
        "cascade.codeComponent" "element.component.architecture-browser"
    }
    include code_browse_controller code_browse_snapshot code_browse_projection code_browse_resource
    autoLayout lr
}

custom "cascade-dashboard-code" {
    title "Dashboard and audit reads — Code"
    properties {
        "cascade.codeComponent" "element.component.dashboard"
    }
    include code_dashboard_router code_dashboard_render code_dashboard_audit code_dashboard_reader code_dashboard_open_reviews code_dashboard_review_projection code_dashboard_review_ui code_dashboard_progress_ui code_dashboard_transcript_ui
    include code_dashboard_lifecycle_ui code_dashboard_board_refresh code_dashboard_plan_approval code_dashboard_post
    include code_dashboard_recovery code_dashboard_incidents code_dashboard_progress_contract code_dashboard_chat_get code_dashboard_transcript_get code_dashboard_chat_page code_dashboard_chat_read code_dashboard_chat_detail code_dashboard_chat_publish code_dashboard_chat_append code_dashboard_chat_fence code_dashboard_chat_source_fence code_dashboard_chat_index code_dashboard_chat_existing_index code_dashboard_chat_rewrite code_dashboard_chat_move code_dashboard_chat_resume_move code_dashboard_recovery_milestone code_dashboard_transcript code_dashboard_backfill
    autoLayout lr
}

custom "cascade-workspace-commands-code" {
    title "Workspace commands — Code"
    properties {
        "cascade.codeComponent" "element.component.workspace-commands"
    }
    include code_cli_main code_cli_up code_cli_worker
    include code_cli_launcher code_cli_drain code_cli_status
    include code_cli_runtime_authority code_cli_loaded_runtime code_cli_validate_runtime code_cli_host_verify_runtime code_cli_current_runtime
    autoLayout lr
}

custom "cascade-diagnostics-code" {
    title "Repository diagnostics — Code"
    properties {
        "cascade.codeComponent" "element.component.diagnostics"
    }
    include code_probe_command code_probe_workspace code_probe_lifecycle
    autoLayout lr
}

custom "cascade-workspace-code" {
    title "Workspace — Code"
    properties {
        "cascade.codeComponent" "element.component.workspace"
    }
    include code_workspace_ownership code_workspace_store code_workspace_closure code_workspace_publish code_review_union code_review_layout code_review_scheduler
    include code_workspace_resolve code_workspace_doc_owner code_workspace_mutation_owner code_workspace_board code_workspace_select code_workspace_registry code_workspace_create code_workspace_resume_epic code_workspace_persist code_workspace_descendant_proof code_workspace_retire code_workspace_preflight
    include code_workspace_invoke code_workspace_owner_live code_workspace_queue_kickoff code_workspace_kickoff_live code_workspace_live_begin code_workspace_live_refresh
    include code_workspace_delivery code_workspace_resume code_workspace_schedule code_workspace_delivery_locked code_workspace_retained_feature
    autoLayout lr
}
