// SPDX-License-Identifier: GPL-2.0-only
/*
 * Minimal ASoC card for the Nokia Lumia 1520 (RM-940) WCD9320.
 *
 * WHAT THIS IS FOR
 *
 * The WCD9320 RX DAI and its SLIMbus slave-port programming path are already
 * proven on hardware (wcd9320-rx-dai-proven), but they were reached through a
 * research hook because ASoC never calls a DAI on a component no card has
 * bound. This card exists to close exactly that gap: to make the framework
 * itself invoke wcd9320-slim-rx1's hw_params(), so the production path has
 * been entered by ASoC and not only by hand.
 *
 * It is a laboratory fixture, not a product topology.
 *
 * WHY THE CPU AND PLATFORM ARE DUMMIES
 *
 * CONFIG_SND_SOC_QCOM is not set on this port: there is no q6afe, no q6asm,
 * no q6routing, so there is no CPU DAI to link against. Enabling that whole
 * front end would drag q6 DT nodes and live ADSP audio services into a
 * milestone meant to prove framework plumbing, so the CPU side is ASoC's
 * dummy and the platform side is the dummy platform.
 *
 * The consequence is deliberate and must not be papered over: the dummy
 * platform provides only .open and has no pcm_construct, so there is NO DMA
 * buffer. A PCM node appears and can be opened and configured, but samples
 * cannot be written. hw_params() runs; a subsequent write fails. That is the
 * expected shape of a successful experiment here.
 *
 * When the q6 work lands, the CPU slot changes and nothing else does -- which
 * is the reason this lives in its own module and the codec driver knows
 * nothing about Lumia card topology.
 *
 * COMP_DUMMY() IS NOT VALID FOR THE PLATFORM SLOT
 *
 * soc-core.c: "COMP_DUMMY() creates size 0 array on dai_link. Fill it as
 * dummy DAI in case of CPU/Codec here. Do nothing for Platform."
 *
 * COMP_DUMMY() is an empty macro; the zero-sized array is the signal, and the
 * core substitutes snd_soc_dummy_dlc for CPU and codec only. A COMP_DUMMY()
 * platform slot would not fail loudly -- it would stay zero-sized and resolve
 * no platform component at all. So the platform is named explicitly.
 */

#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/platform_device.h>

#include <sound/pcm.h>
#include <sound/soc.h>

#define DRV_NAME "wcd9320-lumia-card"

/*
 * The codec component name is a DEVICE name, and device names are not an ABI.
 * It has been "217:a0:1:0" on every boot recorded on this hardware and derives
 * deterministically from the SLIMbus enumeration address, but it is exposed as
 * a read-only module parameter rather than hardcoded so that:
 *
 *   - the normal hardware path needs no arguments;
 *   - an enumeration change fails VISIBLY instead of silently binding
 *     something else;
 *   - the fixture stays reusable without a device name baked into its logic.
 *
 * There is deliberately no fallback and no scanning. A changed component name
 * is evidence, and the failure path prints both values so it is legible.
 */
static char *codec_component = "217:a0:1:0";
module_param(codec_component, charp, 0444);
MODULE_PARM_DESC(codec_component,
		 "WCD9320 ASoC component (device) name to bind against");

/*
 * The DAI name is fixed on purpose: it is the interface under test. Only the
 * component/device instance name is the unstable part.
 */
#define WCD9320_RX_DAI_NAME "wcd9320-slim-rx1"

/*
 * OUR OWN PLATFORM COMPONENT, because snd-soc-dummy cannot be the sole
 * platform for a card. Measured, not assumed:
 *
 * snd_soc_runtime_calc_hw() fills only channels, rates and formats into
 * runtime->hw. It does NOT set .info, .buffer_bytes_max, .period_bytes_* or
 * .periods_*. Those come from the platform calling
 * snd_soc_set_runtime_hwparams().
 *
 * soc-utils.c's dummy_dma_open() is supposed to install dummy_dma_hardware,
 * but it first walks the rtd's components and returns early if any of them is
 * dummy_platform:
 *
 *     for_each_rtd_components(rtd, i, component)
 *             if (component->driver == &dummy_platform)
 *                     return 0;
 *
 * When snd-soc-dummy IS the platform, that condition is always true of
 * itself, so runtime->hw is never installed and .info stays 0.
 *
 * snd_pcm_hw_constraints_complete() then builds the ACCESS mask FROM
 * hw->info -- with info 0 neither INTERLEAVED nor NONINTERLEAVED is set, the
 * mask is empty, and snd_pcm_open() fails with -EINVAL. ASoC's own open
 * succeeded, so nothing is logged and the failure looks like it came from
 * nowhere. That cost a run to find.
 *
 * This component exists solely to install a sane runtime->hw. It allocates no
 * buffer and moves no data: there is still no DMA, so a write after a
 * successful hw_params will still fail, which is the expected shape here.
 */
static const struct snd_pcm_hardware wcd9320_lumia_pcm_hw = {
	.info			= SNDRV_PCM_INFO_INTERLEAVED |
				  SNDRV_PCM_INFO_BLOCK_TRANSFER,
	.buffer_bytes_max	= 128 * 1024,
	.period_bytes_min	= 4096,
	.period_bytes_max	= 4096 * 2,
	.periods_min		= 2,
	.periods_max		= 128,
};

static int wcd9320_lumia_pcm_open(struct snd_soc_component *component,
				  struct snd_pcm_substream *substream)
{
	snd_soc_set_runtime_hwparams(substream, &wcd9320_lumia_pcm_hw);
	return 0;
}

static const struct snd_soc_component_driver wcd9320_lumia_platform = {
	.name	= "wcd9320-lumia-platform",
	.open	= wcd9320_lumia_pcm_open,
};

SND_SOC_DAILINK_DEFS(wcd9320_rx,
	DAILINK_COMP_ARRAY(COMP_DUMMY()),
	DAILINK_COMP_ARRAY(COMP_CODEC(NULL, WCD9320_RX_DAI_NAME)),
	DAILINK_COMP_ARRAY(COMP_PLATFORM(NULL)));

static struct snd_soc_dai_link wcd9320_lumia_dai_links[] = {
	{
		.name = "WCD9320 SLIM RX1",
		.stream_name = "WCD9320 SLIM RX1 Playback",
		.playback_only = 1,
		SND_SOC_DAILINK_REG(wcd9320_rx),
	},
};

static struct snd_soc_card wcd9320_lumia_card = {
	.name = "wcd9320-lumia",
	.long_name = "Nokia Lumia 1520 WCD9320 (minimal)",
	.dai_link = wcd9320_lumia_dai_links,
	.num_links = ARRAY_SIZE(wcd9320_lumia_dai_links),
};

static int wcd9320_lumia_probe(struct platform_device *pdev)
{
	struct snd_soc_card *card = &wcd9320_lumia_card;
	int ret;

	card->dev = &pdev->dev;

	/*
	 * The platform component must exist before the card binds, so register
	 * it first. It lives on this same device, so ASoC names it after the
	 * device -- which is what the link's platform slot is pointed at below.
	 */
	ret = devm_snd_soc_register_component(&pdev->dev,
					      &wcd9320_lumia_platform, NULL, 0);
	if (ret)
		return dev_err_probe(&pdev->dev, ret,
				     "failed to register the platform component\n");

	/*
	 * Filled at probe rather than at compile time: the codec name comes
	 * from a module parameter, and the platform name is this device's own,
	 * which is not known until now.
	 */
	wcd9320_lumia_dai_links[0].codecs[0].name = codec_component;
	wcd9320_lumia_dai_links[0].platforms[0].name = dev_name(&pdev->dev);

	ret = devm_snd_soc_register_card(&pdev->dev, card);
	if (ret) {
		/*
		 * -EPROBE_DEFER is expected and self-correcting: the codec
		 * component and its DAI may not have registered yet. Anything
		 * else is a real failure, and both names are printed so a
		 * changed enumeration name is immediately legible rather than
		 * hidden behind a generic "component not found".
		 */
		if (ret != -EPROBE_DEFER)
			dev_err(&pdev->dev,
				"failed to register card (%d)\n  codec_component=%s\n  codec_dai=%s\n",
				ret, codec_component, WCD9320_RX_DAI_NAME);
		return ret;
	}

	dev_info(&pdev->dev,
		 "minimal card registered: codec_component=%s codec_dai=%s cpu=dummy platform=%s (own, no DMA)\n",
		 codec_component, WCD9320_RX_DAI_NAME, dev_name(&pdev->dev));
	return 0;
}

static struct platform_driver wcd9320_lumia_driver = {
	.driver = {
		.name = DRV_NAME,
		.pm = &snd_soc_pm_ops,
	},
	.probe = wcd9320_lumia_probe,
};

/*
 * No DT node. The permanent RM-940 topology is explicitly undecided, and a
 * proof fixture should not invent one -- so the module creates its own
 * platform device and binds to it.
 */
static struct platform_device *wcd9320_lumia_pdev;

static int __init wcd9320_lumia_init(void)
{
	int ret;

	ret = platform_driver_register(&wcd9320_lumia_driver);
	if (ret)
		return ret;

	wcd9320_lumia_pdev = platform_device_register_simple(DRV_NAME, -1,
							     NULL, 0);
	if (IS_ERR(wcd9320_lumia_pdev)) {
		platform_driver_unregister(&wcd9320_lumia_driver);
		return PTR_ERR(wcd9320_lumia_pdev);
	}
	return 0;
}
module_init(wcd9320_lumia_init);

static void __exit wcd9320_lumia_exit(void)
{
	platform_device_unregister(wcd9320_lumia_pdev);
	platform_driver_unregister(&wcd9320_lumia_driver);
}
module_exit(wcd9320_lumia_exit);

MODULE_VERSION("lumia-card-rc2");
MODULE_DESCRIPTION("Minimal ASoC card binding the WCD9320 RX DAI on Lumia RM-940");
MODULE_LICENSE("GPL");
MODULE_ALIAS("platform:" DRV_NAME);
