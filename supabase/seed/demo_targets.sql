-- demo_targets.sql
-- The user's own savings targets for the seeded cycles (Rs 25,000 each). The NEW cycle that starts
-- when the September salary is credited has no target on purpose: FinPilot asks the user to set it
-- (the live demo sets Rs 25000).

insert into public.monthly_savings_targets (id, user_id, financial_cycle_id, target_amount)
values
  ('6df2ae73-f42c-5d72-8481-132f26e50148', 'a1b2c3d4-0000-4000-8000-000000000001', 'cbf491f0-38ed-594f-8825-b91ec5f9df9a', 25000),
  ('ab757edb-adb3-5273-a1dd-42fce8ba0bed', 'a1b2c3d4-0000-4000-8000-000000000001', '56a6b6f8-8456-52e3-b391-58167eaca992', 25000),
  ('6ba9ff67-bddc-5d10-ab69-eabc9a77c47b', 'a1b2c3d4-0000-4000-8000-000000000001', '8dbad92d-1cb9-51e7-9970-e591a6f2733f', 25000),
  ('9e44d778-b9f7-51ea-bc9c-0c496fad8563', 'a1b2c3d4-0000-4000-8000-000000000001', '1b237208-5a29-5252-b26d-05b1f1e04d80', 25000),
  ('c09b1bf7-b1f5-5158-a28b-69045d622824', 'a1b2c3d4-0000-4000-8000-000000000001', '15d7f1a6-25de-5a25-a7ed-13af1731e1be', 25000),
  ('4c85eabb-6d5d-555b-b78e-5467aac28e3b', 'a1b2c3d4-0000-4000-8000-000000000001', '5bbf52d1-7f1e-5b75-88ca-18a760f38131', 25000)
on conflict (financial_cycle_id) do nothing;

update public.financial_cycles fc
   set savings_target = t.target_amount
  from public.monthly_savings_targets t
 where t.financial_cycle_id = fc.id and fc.user_id = 'a1b2c3d4-0000-4000-8000-000000000001';
