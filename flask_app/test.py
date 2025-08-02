capital = 1400
weekly_return_under_5 = 0.1
weekly_return_over_5 = 0.05

for i in range(22):
    if capital < 5000:
        capital *= (1 + weekly_return_under_5)
    else:
        capital *= (1 + weekly_return_over_5)

    print(f"Week {i + 1}: Capital = ${capital:.2f}")