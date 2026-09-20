-- demo_goals.sql
-- Long-term goals (separate from the per-cycle savings target and from category budgets):
--   * New Laptop      Rs 20,000 of Rs 60,000 by 31 Mar 2027   (about Rs 6,667 per month needed from 30 Sep 2026)
--   * Emergency Fund  Rs 70,000 of Rs 1,50,000 by 30 Jun 2027 (46.7% complete)
-- Contributions raise the goal's current_amount only; they are not expenses and never touch the ledger.

insert into public.financial_goals
  (id, user_id, name, goal_type, target_amount, current_amount, target_date, priority, status, created_at)
values
  ('1773b86b-b407-5867-a3da-228ae3c67be7', 'a1b2c3d4-0000-4000-8000-000000000001', 'New Laptop', 'PURCHASE', 60000, 20000, '2027-03-31', 'MEDIUM', 'ACTIVE', '2026-04-02 10:00:00+05:30'),
  ('7f24ada5-956c-5a26-8b40-dbdc49993e47', 'a1b2c3d4-0000-4000-8000-000000000001', 'Emergency Fund', 'EMERGENCY_FUND', 150000, 70000, '2027-06-30', 'HIGH', 'ACTIVE', '2026-03-31 12:00:00+05:30')
on conflict (id) do nothing;

insert into public.goal_contributions (id, goal_id, user_id, amount, "timestamp", source, notes)
values
  ('576c8186-8888-5d66-9dbf-4ac84a224fe2', '1773b86b-b407-5867-a3da-228ae3c67be7', 'a1b2c3d4-0000-4000-8000-000000000001', 5000, '2026-05-10 09:30:00+05:30', 'seed', 'Seeded contribution'),
  ('c0840d01-7f7d-593d-8308-3c98b07bea58', '1773b86b-b407-5867-a3da-228ae3c67be7', 'a1b2c3d4-0000-4000-8000-000000000001', 7000, '2026-07-12 09:30:00+05:30', 'seed', 'Seeded contribution'),
  ('2bad3020-56c1-5479-818e-09bbeccfba2c', '1773b86b-b407-5867-a3da-228ae3c67be7', 'a1b2c3d4-0000-4000-8000-000000000001', 8000, '2026-09-05 09:30:00+05:30', 'seed', 'Seeded contribution'),
  ('bef4da9f-5f60-5b12-9f9c-6991ef27d3a4', '7f24ada5-956c-5a26-8b40-dbdc49993e47', 'a1b2c3d4-0000-4000-8000-000000000001', 10000, '2026-03-03 09:30:00+05:30', 'seed', 'Seeded contribution'),
  ('35c659c4-784c-502f-82ef-16aab85b7d39', '7f24ada5-956c-5a26-8b40-dbdc49993e47', 'a1b2c3d4-0000-4000-8000-000000000001', 10000, '2026-04-03 09:30:00+05:30', 'seed', 'Seeded contribution'),
  ('b31404cf-5cd8-5fe5-951b-4ff75fa437bf', '7f24ada5-956c-5a26-8b40-dbdc49993e47', 'a1b2c3d4-0000-4000-8000-000000000001', 10000, '2026-05-03 09:30:00+05:30', 'seed', 'Seeded contribution'),
  ('65630f51-2da7-539c-81d8-c33e91f6f763', '7f24ada5-956c-5a26-8b40-dbdc49993e47', 'a1b2c3d4-0000-4000-8000-000000000001', 10000, '2026-06-03 09:30:00+05:30', 'seed', 'Seeded contribution'),
  ('a5529596-5174-5ad7-8553-ec224dcff39f', '7f24ada5-956c-5a26-8b40-dbdc49993e47', 'a1b2c3d4-0000-4000-8000-000000000001', 10000, '2026-07-03 09:30:00+05:30', 'seed', 'Seeded contribution'),
  ('d3deebeb-857f-5c58-a94d-7820dc9a2ca8', '7f24ada5-956c-5a26-8b40-dbdc49993e47', 'a1b2c3d4-0000-4000-8000-000000000001', 10000, '2026-08-03 09:30:00+05:30', 'seed', 'Seeded contribution'),
  ('2945b9d2-8466-5289-b71b-56d1d161b447', '7f24ada5-956c-5a26-8b40-dbdc49993e47', 'a1b2c3d4-0000-4000-8000-000000000001', 10000, '2026-09-03 09:30:00+05:30', 'seed', 'Seeded contribution')
on conflict (id) do nothing;
