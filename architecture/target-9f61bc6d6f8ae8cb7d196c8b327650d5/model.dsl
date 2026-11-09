operator = person "Operator" "Reviews architecture changes." {
    properties {
        "cascade.semanticId" "element.person.operator"
    }
}

cascade = softwareSystem "Cascade" "Coordinates repository-local delivery." {
    properties {
        "cascade.semanticId" "element.system.cascade"
    }

    supervisor = container "Service" "Runs the local workflow." "Python" {
        properties {
            "cascade.semanticId" "element.container.cascade-supervisor"
        }
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

reviews = operator -> cascade "Reviews architecture changes through" {
    properties {
        "cascade.semanticId" "relationship.operator-reviews-cascade"
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
