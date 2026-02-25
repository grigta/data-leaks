<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import {
		Select,
		SelectTrigger,
		SelectContent,
		SelectItem,
		SelectValue
	} from '$lib/components/ui/select';
	import { Label } from '$lib/components/ui/label';
	import { Input } from '$lib/components/ui/input';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Save from '@lucide/svelte/icons/save';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Check from '@lucide/svelte/icons/check';
	import Shield from '@lucide/svelte/icons/shield';
	import ShieldCheck from '@lucide/svelte/icons/shield-check';
	import ShieldOff from '@lucide/svelte/icons/shield-off';
	import Copy from '@lucide/svelte/icons/copy';
	import Eye from '@lucide/svelte/icons/eye';
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import DollarSign from '@lucide/svelte/icons/dollar-sign';
	import KeyRound from '@lucide/svelte/icons/key-round';
	import {
		getSearchFlow,
		updateSearchFlow,
		getSearchFlowOptions,
		getApiCosts,
		updateApiCosts,
		getSearchbugKeys,
		updateSearchbugKeys,
		getCurrentAdminUser,
		setupTwoFactor,
		confirmTwoFactor,
		disableTwoFactor,
		handleApiError,
		type SearchFlowOption,
		type TwoFactorSetupResponse,
		type SearchbugKeysResponse
	} from '$lib/api/client';
	import { toast } from 'svelte-sonner';
	import { t } from '$lib/i18n';

	// Search Flow State
	let isLoading = $state(true);
	let isSaving = $state(false);
	let currentFlow = $state('sb_manual');
	let selectedFlow = $state('sb_manual');
	let updatedAt = $state<string | null>(null);
	let options = $state<SearchFlowOption[]>([]);
	let saveSuccess = $state(false);

	let hasChanges = $derived(selectedFlow !== currentFlow);

	// 2FA State
	let hasTOTP = $state(false);
	let tfaSetupData = $state<TwoFactorSetupResponse | null>(null);
	let tfaStep = $state<'idle' | 'setup' | 'confirming'>('idle');
	let tfaCode = $state('');
	let tfaIsLoading = $state(false);
	let tfaDisablePassword = $state('');
	let tfaShowDisable = $state(false);
	let tfaDisableLoading = $state(false);
	let tfaShowSecret = $state(false);

	// API Costs State
	let costLabels = $state<Record<string, string>>({});
	let savedCosts = $state<Record<string, string>>({});
	let editCosts = $state<Record<string, string>>({});
	let costsSaving = $state(false);
	let costsSaveSuccess = $state(false);

	let hasCostChanges = $derived(
		Object.keys(savedCosts).some((k) => editCosts[k] !== savedCosts[k])
	);

	// SearchBug Keys State
	let sbKeys = $state<SearchbugKeysResponse | null>(null);
	let sbCoCode = $state('');
	let sbPassword = $state('');
	let sbSaving = $state(false);
	let sbSaveSuccess = $state(false);
	let sbShowPassword = $state(false);

	let hasSbChanges = $derived(sbCoCode.trim() !== '' || sbPassword.trim() !== '');

	// Get label for a flow value
	function getFlowLabel(value: string): string {
		const opt = options.find((o) => o.value === value);
		return opt?.label || value;
	}

	function getFlowDescription(value: string): string {
		const opt = options.find((o) => o.value === value);
		return opt?.description || '';
	}

	function formatDate(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleString('ru-RU', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	async function loadData() {
		isLoading = true;
		try {
			const [flowResp, optionsResp, userResp, costsResp, sbKeysResp] = await Promise.all([
				getSearchFlow(),
				getSearchFlowOptions(),
				getCurrentAdminUser(),
				getApiCosts(),
				getSearchbugKeys()
			]);
			currentFlow = flowResp.search_flow;
			selectedFlow = flowResp.search_flow;
			updatedAt = flowResp.updated_at;
			options = optionsResp.options;
			hasTOTP = userResp.has_totp;
			costLabels = costsResp.labels;
			savedCosts = { ...costsResp.costs };
			editCosts = { ...costsResp.costs };
			sbKeys = sbKeysResp;
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isLoading = false;
		}
	}

	async function handleSave() {
		isSaving = true;
		saveSuccess = false;
		try {
			const resp = await updateSearchFlow(selectedFlow);
			currentFlow = resp.search_flow;
			selectedFlow = resp.search_flow;
			updatedAt = resp.updated_at;
			saveSuccess = true;
			toast.success($t('settings.searchFlow.saved'));
			setTimeout(() => (saveSuccess = false), 2000);
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isSaving = false;
		}
	}

	async function handleEnable2FA() {
		tfaIsLoading = true;
		try {
			tfaSetupData = await setupTwoFactor();
			tfaStep = 'setup';
			tfaCode = '';
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			tfaIsLoading = false;
		}
	}

	async function handleConfirm2FA() {
		if (tfaCode.length !== 6) return;
		tfaIsLoading = true;
		try {
			await confirmTwoFactor(tfaCode);
			hasTOTP = true;
			tfaStep = 'idle';
			tfaSetupData = null;
			tfaCode = '';
			toast.success('Two-Factor Authentication enabled successfully');
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			tfaIsLoading = false;
		}
	}

	function handleCancelSetup() {
		tfaStep = 'idle';
		tfaSetupData = null;
		tfaCode = '';
		tfaShowSecret = false;
	}

	async function handleDisable2FA() {
		if (!tfaDisablePassword) return;
		tfaDisableLoading = true;
		try {
			await disableTwoFactor(tfaDisablePassword);
			hasTOTP = false;
			tfaShowDisable = false;
			tfaDisablePassword = '';
			toast.success('Two-Factor Authentication disabled');
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			tfaDisableLoading = false;
		}
	}

	function copyToClipboard(text: string) {
		navigator.clipboard.writeText(text);
		toast.success('Copied to clipboard');
	}

	async function handleSaveCosts() {
		costsSaving = true;
		costsSaveSuccess = false;
		try {
			const resp = await updateApiCosts(editCosts);
			savedCosts = { ...resp.costs };
			editCosts = { ...resp.costs };
			costsSaveSuccess = true;
			toast.success('API costs saved');
			setTimeout(() => (costsSaveSuccess = false), 2000);
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			costsSaving = false;
		}
	}

	async function handleSaveSearchbugKeys() {
		sbSaving = true;
		sbSaveSuccess = false;
		try {
			const data: Record<string, string> = {};
			if (sbCoCode.trim()) data.co_code = sbCoCode.trim();
			if (sbPassword.trim()) data.password = sbPassword.trim();

			const resp = await updateSearchbugKeys(data);
			sbKeys = resp;
			sbCoCode = '';
			sbPassword = '';
			sbSaveSuccess = true;
			toast.success('SearchBug API keys updated');
			setTimeout(() => (sbSaveSuccess = false), 2000);
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			sbSaving = false;
		}
	}

	onMount(loadData);
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h2 class="text-2xl font-bold">{$t('settings.title')}</h2>
		<Button variant="outline" size="sm" onclick={loadData} disabled={isLoading}>
			<RefreshCw class="mr-2 h-4 w-4" />
			{$t('common.refresh')}
		</Button>
	</div>

	{#if isLoading}
		<div class="flex items-center justify-center py-12">
			<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
		</div>
	{:else}
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center justify-between">
					<span>{$t('settings.searchFlow.title')}</span>
					{#if updatedAt}
						<span class="text-sm font-normal text-muted-foreground">
							{$t('settings.searchFlow.updated', { values: { date: formatDate(updatedAt) } })}
						</span>
					{/if}
				</CardTitle>
			</CardHeader>
			<CardContent class="space-y-6">
				<div class="space-y-2">
					<Label>{$t('settings.searchFlow.label')}</Label>
					<Select
						value={selectedFlow}
						onSelectedChange={(sel) => {
							if (sel?.value) selectedFlow = sel.value;
						}}
					>
						<SelectTrigger class="w-full max-w-md">
							<SelectValue placeholder={$t('settings.searchFlow.placeholder')} />
						</SelectTrigger>
						<SelectContent>
							{#each options as opt}
								<SelectItem value={opt.value}>{opt.label}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
					{#if selectedFlow}
						<p class="text-sm text-muted-foreground">
							{getFlowDescription(selectedFlow)}
						</p>
					{/if}
				</div>

				<!-- Save button -->
				<div class="flex items-center gap-3">
					<Button onclick={handleSave} disabled={!hasChanges || isSaving}>
						{#if isSaving}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							{$t('common.saving')}
						{:else if saveSuccess}
							<Check class="mr-2 h-4 w-4" />
							{$t('common.saved')}
						{:else}
							<Save class="mr-2 h-4 w-4" />
							{$t('common.save')}
						{/if}
					</Button>
					{#if hasChanges}
						<span class="text-sm text-muted-foreground">
							Changing from <strong>{getFlowLabel(currentFlow)}</strong> to
							<strong>{getFlowLabel(selectedFlow)}</strong>
						</span>
					{/if}
				</div>
			</CardContent>
		</Card>

		<!-- API Costs -->
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<DollarSign class="h-5 w-5" />
					API Costs (Cost Price)
				</CardTitle>
			</CardHeader>
			<CardContent class="space-y-4">
				<p class="text-sm text-muted-foreground">
					Cost price per API request. Used for profit calculations in analytics.
				</p>
				<div class="grid gap-4 sm:grid-cols-3">
					{#each Object.entries(costLabels) as [key, label]}
						<div class="space-y-1.5">
							<Label for={key}>{label}</Label>
							<div class="relative">
								<span class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">$</span>
								<Input
									id={key}
									type="number"
									step="0.01"
									min="0"
									bind:value={editCosts[key]}
									class="pl-7"
								/>
							</div>
						</div>
					{/each}
				</div>
				<div class="flex items-center gap-3">
					<Button onclick={handleSaveCosts} disabled={!hasCostChanges || costsSaving}>
						{#if costsSaving}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							{$t('common.saving')}
						{:else if costsSaveSuccess}
							<Check class="mr-2 h-4 w-4" />
							{$t('common.saved')}
						{:else}
							<Save class="mr-2 h-4 w-4" />
							{$t('common.save')}
						{/if}
					</Button>
					{#if hasCostChanges}
						<Button variant="outline" onclick={() => (editCosts = { ...savedCosts })} size="sm">
							Reset
						</Button>
					{/if}
				</div>
			</CardContent>
		</Card>

		<!-- SearchBug API Keys -->
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center justify-between">
					<span class="flex items-center gap-2">
						<KeyRound class="h-5 w-5" />
						SearchBug API Keys
					</span>
					{#if sbKeys}
						<Badge variant={sbKeys.source === 'database' ? 'default' : 'secondary'}>
							{sbKeys.source === 'database' ? 'Database' : 'Env vars'}
						</Badge>
					{/if}
				</CardTitle>
			</CardHeader>
			<CardContent class="space-y-4">
				<p class="text-sm text-muted-foreground">
					SearchBug API credentials. Changes apply immediately without restart.
				</p>

				{#if sbKeys}
					<div class="rounded-md border p-3 text-sm space-y-1">
						<p>CO_CODE: <code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{sbKeys.co_code || 'Not set'}</code></p>
						<p>Password: <span class="font-medium">{sbKeys.has_password ? 'Set' : 'Not set'}</span></p>
						{#if sbKeys.updated_at}
							<p class="text-muted-foreground text-xs">Updated: {formatDate(sbKeys.updated_at)}</p>
						{/if}
					</div>
				{/if}

				<div class="grid gap-4 sm:grid-cols-2">
					<div class="space-y-1.5">
						<Label for="sb_co_code">New CO_CODE</Label>
						<Input
							id="sb_co_code"
							type="text"
							placeholder="Leave empty to keep current"
							bind:value={sbCoCode}
						/>
					</div>
					<div class="space-y-1.5">
						<Label for="sb_password">New Password</Label>
						<div class="relative">
							<Input
								id="sb_password"
								type={sbShowPassword ? 'text' : 'password'}
								placeholder="Leave empty to keep current"
								bind:value={sbPassword}
							/>
							<button
								type="button"
								class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
								onclick={() => (sbShowPassword = !sbShowPassword)}
							>
								{#if sbShowPassword}
									<EyeOff class="h-4 w-4" />
								{:else}
									<Eye class="h-4 w-4" />
								{/if}
							</button>
						</div>
					</div>
				</div>

				<div class="flex items-center gap-3">
					<Button onclick={handleSaveSearchbugKeys} disabled={!hasSbChanges || sbSaving}>
						{#if sbSaving}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							{$t('common.saving')}
						{:else if sbSaveSuccess}
							<Check class="mr-2 h-4 w-4" />
							{$t('common.saved')}
						{:else}
							<Save class="mr-2 h-4 w-4" />
							{$t('common.save')}
						{/if}
					</Button>
					{#if hasSbChanges}
						<Button
							variant="outline"
							onclick={() => {
								sbCoCode = '';
								sbPassword = '';
							}}
							size="sm"
						>
							Reset
						</Button>
					{/if}
				</div>
			</CardContent>
		</Card>

		<!-- Two-Factor Authentication -->
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center justify-between">
					<span class="flex items-center gap-2">
						<Shield class="h-5 w-5" />
						Two-Factor Authentication
					</span>
					{#if hasTOTP}
						<Badge variant="default" class="bg-green-600 text-white">Enabled</Badge>
					{:else}
						<Badge variant="secondary">Disabled</Badge>
					{/if}
				</CardTitle>
			</CardHeader>
			<CardContent class="space-y-4">
				{#if hasTOTP && tfaStep === 'idle'}
					<!-- 2FA is enabled -->
					<div class="flex items-center gap-3 rounded-md border border-green-200 bg-green-50 p-4 dark:border-green-900 dark:bg-green-950">
						<ShieldCheck class="h-5 w-5 text-green-600 dark:text-green-400" />
						<p class="text-sm text-green-700 dark:text-green-300">
							Your account is protected with two-factor authentication.
						</p>
					</div>

					{#if !tfaShowDisable}
						<Button variant="destructive" onclick={() => (tfaShowDisable = true)}>
							<ShieldOff class="mr-2 h-4 w-4" />
							Disable 2FA
						</Button>
					{:else}
						<div class="space-y-3 rounded-md border p-4">
							<p class="text-sm font-medium">Enter your password to disable 2FA:</p>
							<Input
								type="password"
								placeholder="Password"
								bind:value={tfaDisablePassword}
								onkeydown={(e) => { if (e.key === 'Enter') handleDisable2FA(); }}
							/>
							<div class="flex gap-2">
								<Button
									variant="destructive"
									onclick={handleDisable2FA}
									disabled={!tfaDisablePassword || tfaDisableLoading}
								>
									{#if tfaDisableLoading}
										<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									{/if}
									Confirm Disable
								</Button>
								<Button
									variant="outline"
									onclick={() => { tfaShowDisable = false; tfaDisablePassword = ''; }}
								>
									Cancel
								</Button>
							</div>
						</div>
					{/if}
				{:else if tfaStep === 'idle'}
					<!-- 2FA is disabled -->
					<p class="text-sm text-muted-foreground">
						Add an extra layer of security to your account by enabling two-factor authentication with an authenticator app.
					</p>
					<Button onclick={handleEnable2FA} disabled={tfaIsLoading}>
						{#if tfaIsLoading}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						{:else}
							<Shield class="mr-2 h-4 w-4" />
						{/if}
						Enable 2FA
					</Button>
				{:else if tfaStep === 'setup' && tfaSetupData}
					<!-- Setup step: show QR + secret + confirm -->
					<div class="space-y-4">
						<p class="text-sm text-muted-foreground">
							Scan the QR code below with your authenticator app (Google Authenticator, Authy, etc.):
						</p>

						<!-- QR Code -->
						<div class="flex justify-center rounded-md border bg-white p-4">
							<img
								src={tfaSetupData.qr_code}
								alt="2FA QR Code"
								class="h-48 w-48"
							/>
						</div>

						<!-- Manual secret -->
						<div class="space-y-2">
							<p class="text-sm font-medium">Or enter this secret manually:</p>
							<div class="flex items-center gap-2">
								<code class="flex-1 rounded-md border bg-muted px-3 py-2 text-sm font-mono">
									{#if tfaShowSecret}
										{tfaSetupData.secret}
									{:else}
										{'*'.repeat(tfaSetupData.secret.length)}
									{/if}
								</code>
								<Button
									variant="outline"
									size="icon"
									onclick={() => (tfaShowSecret = !tfaShowSecret)}
								>
									{#if tfaShowSecret}
										<EyeOff class="h-4 w-4" />
									{:else}
										<Eye class="h-4 w-4" />
									{/if}
								</Button>
								<Button
									variant="outline"
									size="icon"
									onclick={() => copyToClipboard(tfaSetupData!.secret)}
								>
									<Copy class="h-4 w-4" />
								</Button>
							</div>
						</div>

						<!-- Verification code input -->
						<div class="space-y-2">
							<Label>Enter the 6-digit code from your authenticator app:</Label>
							<Input
								type="text"
								inputmode="numeric"
								maxlength={6}
								placeholder="000000"
								bind:value={tfaCode}
								class="max-w-[200px] text-center text-lg font-mono tracking-widest"
								onkeydown={(e) => { if (e.key === 'Enter') handleConfirm2FA(); }}
							/>
						</div>

						<div class="flex gap-2">
							<Button
								onclick={handleConfirm2FA}
								disabled={tfaCode.length !== 6 || tfaIsLoading}
							>
								{#if tfaIsLoading}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
								{:else}
									<Check class="mr-2 h-4 w-4" />
								{/if}
								Confirm
							</Button>
							<Button variant="outline" onclick={handleCancelSetup}>
								Cancel
							</Button>
						</div>
					</div>
				{/if}
			</CardContent>
		</Card>
	{/if}
</div>
