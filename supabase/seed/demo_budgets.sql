-- demo_budgets.sql
-- Category budgets. Separate from the savings target; measured against the active cycle.

insert into public.budgets (id, user_id, category, amount)
values
  ('a2f91e23-f07d-592f-843a-0129ec2bead8', 'a1b2c3d4-0000-4000-8000-000000000001', 'Food', 7000),
  ('0c5b7f84-64d4-5ff9-a392-a98d92dc8266', 'a1b2c3d4-0000-4000-8000-000000000001', 'Shopping', 6000),
  ('cbf73e88-877b-5287-b617-b64aacfbd360', 'a1b2c3d4-0000-4000-8000-000000000001', 'Transport', 4000),
  ('15419814-1756-5c55-a421-4440c008b700', 'a1b2c3d4-0000-4000-8000-000000000001', 'Entertainment', 2000)
on conflict (user_id, category) do nothing;
