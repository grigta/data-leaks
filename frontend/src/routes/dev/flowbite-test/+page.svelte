<script>
	import { Button as FlowbiteButton, Dropdown, DropdownItem } from 'flowbite-svelte';
	import { Button } from '$lib/components/ui/button';
</script>

<div class="container mx-auto p-8 space-y-8">
	<h1 class="text-3xl font-bold mb-6">Flowbite + bits-ui Compatibility Test</h1>

	<section class="space-y-4 border border-border p-6 rounded-lg">
		<h2 class="text-2xl font-semibold">Light Theme Components</h2>

		<div class="space-y-4">
			<div>
				<h3 class="text-lg font-medium mb-2">Flowbite Button</h3>
				<FlowbiteButton>Flowbite Button</FlowbiteButton>
				<FlowbiteButton color="alternative">Alternative</FlowbiteButton>
				<FlowbiteButton color="dark">Dark</FlowbiteButton>
			</div>

			<div>
				<h3 class="text-lg font-medium mb-2">bits-ui Button</h3>
				<Button>bits-ui Button</Button>
				<Button variant="secondary">Secondary</Button>
				<Button variant="outline">Outline</Button>
			</div>
		</div>
	</section>

	<section class="space-y-4 border border-border p-6 rounded-lg">
		<h2 class="text-2xl font-semibold">Dark Theme Test</h2>
		<div class="dark bg-background p-6 rounded-lg space-y-4">
			<div>
				<h3 class="text-lg font-medium mb-2 text-foreground">Flowbite Button (Dark)</h3>
				<FlowbiteButton>Flowbite Button</FlowbiteButton>
				<FlowbiteButton color="alternative">Alternative</FlowbiteButton>
				<FlowbiteButton color="dark">Dark</FlowbiteButton>
			</div>

			<div>
				<h3 class="text-lg font-medium mb-2 text-foreground">bits-ui Button (Dark)</h3>
				<Button>bits-ui Button</Button>
				<Button variant="secondary">Secondary</Button>
				<Button variant="outline">Outline</Button>
			</div>
		</div>
	</section>

	<section class="space-y-4 border border-border p-6 rounded-lg">
		<h2 class="text-2xl font-semibold">Dropdown Components</h2>

		<div class="space-y-4">
			<div>
				<h3 class="text-lg font-medium mb-2">Flowbite Dropdown</h3>
				<FlowbiteButton id="dropdown-btn">Flowbite Dropdown</FlowbiteButton>
				<Dropdown triggeredBy="#dropdown-btn">
					<DropdownItem>Item 1</DropdownItem>
					<DropdownItem>Item 2</DropdownItem>
					<DropdownItem>Item 3</DropdownItem>
				</Dropdown>
			</div>

			<div>
				<h3 class="text-lg font-medium mb-2">Notes</h3>
				<p class="text-muted-foreground">
					Check that both component libraries render correctly without style conflicts. Verify
					colors, spacing, and hover states in both light and dark themes.
				</p>
			</div>
		</div>
	</section>
</div>
