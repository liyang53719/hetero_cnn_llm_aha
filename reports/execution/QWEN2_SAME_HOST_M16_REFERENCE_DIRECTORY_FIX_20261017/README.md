# Same-host M16 scalar-reference directory fix

Status: source/cold reviewed. This revision has not executed the producer or full M16.

The preceding hosted run 39000095742 on af3d9d3b49d9680988cec859f4768e6a974f2538 failed in the scalar-reference command boundary after 74.110056551 seconds. The parent observed exit 1 and complete owned-process cleanup. A bounded diagnostic retained ValueError and pinned source frames. The original nested child stderr and precise exit cause were not retained. Earlier returned functions do not establish qualification without their receipts.

Source inspection establishes an output-directory contract defect: the original scalar reference requires raw_stages to exist before launch, but the driver did not create it. This revision exclusively creates that role-specific private directory with mode 0700 immediately before the unchanged owned command. Existing directory, file, or symlink collisions fail closed. Both generated reference sources and all arithmetic, validation, ownership, phase budgets, and acceptance rules remain unchanged.

Cold validation passed 166 tests in each of normal and optimized Python, including both role boundaries and all six collision cases. The unchanged old driver fails the new boundary negative controls. Three genuine isolated entry boundaries and a 357-file worktree composition passed. These checks installed no packages, accessed no weights, compiled no native code, and ran no numerical model. Local checks used Python 3.12.14; the hosted requirement remains Python 3.12.15.

The six-file source delta includes driver/tests and their source bindings plus a workflow revision comment. The 356-file static composed map changes only driver.py and test_driver.py; its other 354 entries remain exact. The complete runtime closure is 381 files. A complete Git object audit must verify the actual new candidate commit before publication is claimed complete. The dynamic source contract must bind that actual trigger commit.

The prior failure evidence remains preserved. No producer qualification, full M16, full M128, RTL, or hardware acceptance is claimed by this source repair.
