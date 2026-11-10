workspace "Renderer node join proof" {
    model {
        platform = softwareSystem "Platform" {
            properties {
                "cascade.id" "system.platform"
            }

            first = container "Worker" {
                properties {
                    "cascade.id" "container.worker.first"
                }
            }

        }

        auxiliary = softwareSystem "Auxiliary" {
            properties {
                "cascade.id" "system.auxiliary"
            }

            second = container "Worker" {
                properties {
                    "cascade.id" "container.worker.second"
                }
            }
        }

        reads = first -> second "Reads" {
            properties {
                "cascade.id" "relationship.first.second.reads"
            }
        }

        writes = first -> second "Writes" {
            properties {
                "cascade.id" "relationship.first.second.writes"
            }
        }

        deploymentEnvironment "Live" {
            firstCloud = deploymentNode "Cloud A" {
                properties {
                    "cascade.id" "deployment.cloud.first"
                }
                firstRegion = deploymentNode "Region" {
                    properties {
                        "cascade.id" "deployment.region.first"
                    }
                    firstInstance = containerInstance first
                }
            }

            secondCloud = deploymentNode "Cloud B" {
                properties {
                    "cascade.id" "deployment.cloud.second"
                }
                secondRegion = deploymentNode "Region" {
                    properties {
                        "cascade.id" "deployment.region.second"
                    }
                    secondInstance = containerInstance second
                }
            }
        }
    }

    views {
        deployment * "Live" "renderer-node-join" {
            include *
            autoLayout lr
        }
    }
}
