from pulp import LpMaximize, LpProblem, LpStatus, LpVariable, lpSum


def create_profit_optimizer():
    # Create the optimization model
    model = LpProblem(name="profit-optimization", sense=LpMaximize)

    # Define decision variables (production quantities)
    products = range(1, 5)  # 4 products
    x = {i: LpVariable(name=f"product_{i}", lowBound=0) for i in products}

    # Define profit per unit for each product
    profit_per_unit = {1: 20, 2: 12, 3: 40, 4: 25}

    # Set the objective function (maximize total profit)
    model += lpSum([profit_per_unit[i] * x[i] for i in products])

    # Add constraints
    # Constraint 1: Total production capacity (max 50 units)
    model += (lpSum(x.values()) <= 50, "production_capacity")

    # Constraint 2: Raw material A availability
    model += (3 * x[1] + 2 * x[2] + x[3] + 0 * x[4] <= 100, "material_A")

    # Constraint 3: Raw material B availability
    model += (x[1] + 2 * x[2] + 3 * x[3] + 0 * x[4] <= 90, "material_B")

    return model, x


def solve_and_display_results(model, x):
    # Solve the optimization problem
    model.solve()

    # Display results
    print(f"Status: {LpStatus[model.status]}")
    print(f"Maximum Profit: ${model.objective.value():.2f}")
    print("\nOptimal Production Quantities:")
    for var in x.values():
        print(f"  {var.name}: {var.value():.2f} units")

    return model.objective.value(), {var.name: var.value() for var in x.values()}


# Advanced Features (as provided by the user, but not integrated into the
# main optimizer for this example)
def add_price_optimization(_model, base_price, price_elasticity):
    # Add price as a decision variable
    price = LpVariable(
        name="price", lowBound=base_price * 0.8, upBound=base_price * 1.2
    )

    # Modify demand based on price elasticity
    demand = 100 - price_elasticity * (price - base_price)

    # Update profit calculation
    return price, demand


def scenario_analysis(constraints_list):
    results = []
    for scenario_name, constraints in constraints_list:
        model, x = create_profit_optimizer()
        # Apply scenario-specific constraints
        for constraint in constraints:
            model += constraint

        model.solve()
        if model.solve() == 1:  # Optimal solution found
            results.append(
                {
                    "scenario": scenario_name,
                    "profit": model.objective.value(),
                    "production": {v.name: v.value() for v in x.values()},
                }
            )
    return results


if __name__ == "__main__":
    print("Running basic profit optimization example...")
    model, x = create_profit_optimizer()
    profit, production_quantities = solve_and_display_results(model, x)
    print(
        "\nBasic Profit Optimizer setup complete. You can now import and use create_profit_optimizer and solve_and_display_results functions from basic_profit_optimizer.py."
    )
