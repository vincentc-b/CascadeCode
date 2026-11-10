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
        }
    }

    views {
        deployment * "Live" "renderer-node-join" {
            include *
            autoLayout lr
        }
    }
}
