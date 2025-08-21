from pulp import LpMaximize, LpProblem, LpVariable, lpSum, LpStatus

def create_profit_optimizer():
    # Create the optimization model
    model = LpProblem(name="profit-optimization", sense=LpMaximize)
    
    # Define decision variables (production quantities)
    products = range(1, 4 + 1)  # 4 products
    x = {i: LpVariable(name=f"product_{i}", lowBound=0) for i in products}
    
    # Define profit per unit for each product
    profit_per_unit = {1: 20, 2: 12, 3: 40, 4: 25}
    
    # Set the objective function (maximize total profit)
    model += lpSum([profit_per_unit[i] * x[i] for i in products])
    
    # Add constraints
    # Constraint 1: Total production capacity (max 50 units)
    model += (lpSum(x.values()) <= 50, "production_capacity")
    
    # Constraint 2: Raw material A availability
    model += (3*x[1] + 2*x[2] + x[3] + 4*x[4] <= 100, "material_A")
    
    # Constraint 3: Raw material B availability
    model += (x[1] + 2*x[2] + 3*x[3] + 2*x[4] <= 90, "material_B")
    
    return model, x

def solve_and_display_results(model, x):
    # Solve the optimization problem
    status = model.solve()
    
    # Display results
    print(f"Status: {LpStatus[model.status]}")
    print(f"Maximum Profit: ${model.objective.value():.2f}")
    print("\nOptimal Production Quantities:")
    for var in x.values():
        print(f"  {var.name}: {var.value():.2f} units")
    
    return model.objective.value(), {var.name: var.value() for var in x.values()}

if __name__ == "__main__":
    model, x = create_profit_optimizer()
    solve_and_display_results(model, x)
