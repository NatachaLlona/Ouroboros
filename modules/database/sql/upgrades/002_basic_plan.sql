-- Bootstrap already activates Plan 1 and its mandatory Database/API modules.
-- Give this plan its product name without changing installation entitlements.
UPDATE {plan} SET name='Basic (Plan 1: Database + API Integration)'
WHERE plan_number=1 AND name='Plan 1';
