// SPDX-License-Identifier: GPL-2.0
/*
 * Lumia 1520 (RM-940): the PM8941 MCLK path, as an EXPERIMENT.
 *
 * WHAT THIS IS FOR
 *
 * Two WCD9320 registers refuse writes on this board -- CDC_CLK_POWER_CTL
 * (0x314) and CDC_CLK_RDAC_CLK_EN_CTL (0x30d) bit 1 -- while the whole digital
 * RX path accepts everything. The codec's own rate selector, CHIP_CTL[2:1],
 * offers only 12.288 MHz or 9.6 MHz, so it cannot run from the raw 19.2 MHz
 * XO; the board is supposed to feed it 9.6 MHz. This establishes that clock so
 * the refusal can be re-tested against it.
 *
 * WHY IT IS NOT A CLOCK PROVIDER
 *
 * r166 tried mainline's clk-spmi-pmic-div here and broke the boot. That driver
 * registers CCF clocks named div_clk1..N, and MSM8974's RPM already exports
 * div_clk1, so registration failed with -EEXIST, took the RPM clock controller
 * down with it, and the eMMC lost regulator support. On this SoC the two cannot
 * coexist.
 *
 * Downstream did not have that problem because its equivalent, qpnp-clkdiv,
 * exposed a private API (qpnp_clkdiv_get/_enable/_config) and registered no CCF
 * clocks at all. This follows that shape: it programs the divider and nothing
 * else. RPM keeps ownership of the enable vote, which the codec takes through
 * <&rpmcc RPM_SMD_DIV_A_CLK1> as a normal consumer.
 *
 * WHERE THE VALUES COME FROM
 *
 * A shipping MSM8974 + WCD9320 board, the Nexus 5:
 *
 *   msm8974-clock.dtsi   pm8941_clkdiv1: clkdiv@5b00 { qcom,cxo-div = <2>; }
 *   hammerhead.dtsi      taiko-mclk-clk = <&pm8941_clkdiv1>;
 *                        qcom,taiko-mclk-clk-freq = <9600000>;
 *                        qcom,cdc-mclk-gpios = <&pm8941_gpios 15 0>;
 *
 * and the encoding is corroborated twice over: downstream's
 * Q_CLKDIV_XO_DIV_2 is 2, and mainline's div_to_div_factor(2) is
 * ilog2(2) + 1 = 2. So DIV_CTL1 = 2 means XO/2 = 9.6 MHz.
 *
 * DELIBERATELY EXPERIMENTAL
 *
 * This is a separate file, a separate node, and driven entirely from sysfs. It
 * does NOT run at probe and the WCD9320 driver does not reach into the PMIC.
 * Whether permanent ownership of this configuration belongs here, in a board
 * file, or somewhere else is a question for after the hardware answers.
 */

#include <linux/device.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/pinctrl/consumer.h>
#include <linux/regmap.h>
#include <linux/spmi.h>
#include <linux/sysfs.h>

/* PM8941 CLKDIV peripheral, relative to the node's own reg base. */
#define LUMIA_DIV_CTL1			0x43
#define LUMIA_DIV_CTL1_FACTOR_MASK	0x07
#define LUMIA_EN_CTL			0x46
#define LUMIA_EN_CTL_ENABLE		0x80

/*
 * Downstream: Q_CLKDIV_XO_DIV_2 = 2 in enum q_clkdiv_cfg.
 * Mainline:   div_to_div_factor(2) = min(ilog2(2) + 1, 7) = 2.
 * Two independent implementations, same encoding.
 */
#define LUMIA_XO_DIV_2			2

/*
 * PM8941 GPIO 15, read only, so the evidence can show the pad's mux and the
 * divider factor from one place and at one instant. gpioN lives at
 * 0xc000 + (N - 1) * 0x100, so gpio15 is 0xce00, and MODE_CTL is +0x40.
 * Confirmed against the PM8941 dtsi, which puts qcom,pin-num = <15> at 0xce00.
 */
#define LUMIA_GPIO15_MODE_CTL		0xce40

struct lumia_mclk {
	struct device *dev;
	struct regmap *regmap;
	u32 base;

	struct pinctrl *pinctrl;
	struct pinctrl_state *state_off;
	struct pinctrl_state *state_divclk;

	bool applied;
	u8 div_pre;			/* DIV_CTL1 as measured before we wrote */
	bool div_pre_valid;
};

static int lumia_read(struct lumia_mclk *m, unsigned int reg, unsigned int *val)
{
	/*
	 * Bypassed: if this regmap ever gains a cache, a cached read here would
	 * report our own write back to us, which is precisely the failure this
	 * experiment exists to avoid.
	 */
	return regmap_read_bypassed(m->regmap, reg, val);
}

static int lumia_mclk_apply(struct lumia_mclk *m, bool on)
{
	unsigned int val;
	int ret;

	if (on) {
		if (m->applied) {
			dev_err(m->dev, "mclk-div: already applied\n");
			return -EBUSY;
		}

		ret = lumia_read(m, m->base + LUMIA_DIV_CTL1, &val);
		if (ret)
			return ret;
		m->div_pre = val & 0xff;
		m->div_pre_valid = true;
		dev_info(m->dev, "mclk-div: DIV_CTL1 measured %02x before any write\n",
			 val & 0xff);

		ret = regmap_update_bits(m->regmap, m->base + LUMIA_DIV_CTL1,
					 LUMIA_DIV_CTL1_FACTOR_MASK,
					 LUMIA_XO_DIV_2);
		if (ret) {
			dev_err(m->dev, "mclk-div: DIV_CTL1 write failed: %d\n", ret);
			return ret;
		}

		ret = lumia_read(m, m->base + LUMIA_DIV_CTL1, &val);
		if (ret)
			return ret;
		if ((val & LUMIA_DIV_CTL1_FACTOR_MASK) != LUMIA_XO_DIV_2) {
			dev_err(m->dev,
				"mclk-div: DIV_CTL1 did not take: chip reads %02x, wanted factor %u\n",
				val & 0xff, LUMIA_XO_DIV_2);
			return -EIO;
		}
		dev_info(m->dev, "mclk-div: DIV_CTL1 = %02x, factor %u -> XO/2\n",
			 val & 0xff, val & LUMIA_DIV_CTL1_FACTOR_MASK);

		if (m->state_divclk) {
			ret = pinctrl_select_state(m->pinctrl, m->state_divclk);
			if (ret) {
				dev_err(m->dev, "mclk-div: pinmux to divclk failed: %d\n",
					ret);
				return ret;
			}
			lumia_read(m, LUMIA_GPIO15_MODE_CTL, &val);
			dev_info(m->dev,
				 "mclk-div: gpio15 MODE_CTL = %02x (dir %u, function %u)\n",
				 val & 0xff, (val >> 4) & 0x7, (val >> 1) & 0x7);
		}

		m->applied = true;
		dev_info(m->dev, "mclk-div: APPLIED\n");
		return 0;
	}

	if (!m->applied) {
		dev_warn(m->dev, "mclk-div: not applied, nothing to restore\n");
		return 0;
	}

	if (m->state_off)
		pinctrl_select_state(m->pinctrl, m->state_off);

	if (m->div_pre_valid) {
		regmap_update_bits(m->regmap, m->base + LUMIA_DIV_CTL1,
				   LUMIA_DIV_CTL1_FACTOR_MASK,
				   m->div_pre & LUMIA_DIV_CTL1_FACTOR_MASK);
		dev_info(m->dev, "mclk-div: DIV_CTL1 restored to factor %u\n",
			 m->div_pre & LUMIA_DIV_CTL1_FACTOR_MASK);
	}

	m->applied = false;
	dev_info(m->dev, "mclk-div: RESTORED\n");
	return 0;
}

static ssize_t mclk_div_test_store(struct device *dev,
				   struct device_attribute *attr,
				   const char *buf, size_t len)
{
	struct lumia_mclk *m = dev_get_drvdata(dev);
	int ret;

	if (sysfs_streq(buf, "on"))
		ret = lumia_mclk_apply(m, true);
	else if (sysfs_streq(buf, "off"))
		ret = lumia_mclk_apply(m, false);
	else
		return -EINVAL;

	return ret ? ret : len;
}
static DEVICE_ATTR_WO(mclk_div_test);

/*
 * Everything the gate needs about the external path, read from the PMIC at the
 * moment it is asked -- the divider factor, the enable bit, and the pad's mux.
 *
 * clk_get_rate() is deliberately absent. The RPM clock is a branch whose
 * recalc_rate reports a fixed nominal 19.2 MHz and never reads DIV_CTL1, so it
 * cannot witness the physical divider. This register can.
 */
static ssize_t mclk_div_state_show(struct device *dev,
				   struct device_attribute *attr, char *buf)
{
	struct lumia_mclk *m = dev_get_drvdata(dev);
	unsigned int div = 0, en = 0, mode = 0;

	lumia_read(m, m->base + LUMIA_DIV_CTL1, &div);
	lumia_read(m, m->base + LUMIA_EN_CTL, &en);
	lumia_read(m, LUMIA_GPIO15_MODE_CTL, &mode);

	return sysfs_emit(buf,
			  "applied=%u base=0x%04x\n"
			  "div_ctl1=%02x factor=%u\n"
			  "en_ctl=%02x enabled=%u\n"
			  "gpio15_mode_ctl=%02x dir=%u function=%u\n",
			  m->applied ? 1 : 0, m->base,
			  div & 0xff, div & LUMIA_DIV_CTL1_FACTOR_MASK,
			  en & 0xff, (en & LUMIA_EN_CTL_ENABLE) ? 1 : 0,
			  mode & 0xff, (mode >> 4) & 0x7, (mode >> 1) & 0x7);
}
static DEVICE_ATTR_RO(mclk_div_state);

static struct attribute *lumia_mclk_attrs[] = {
	&dev_attr_mclk_div_test.attr,
	&dev_attr_mclk_div_state.attr,
	NULL,
};
ATTRIBUTE_GROUPS(lumia_mclk);

static int lumia_mclk_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct lumia_mclk *m;
	struct spmi_device *pmic;
	unsigned int val;
	int ret;

	m = devm_kzalloc(dev, sizeof(*m), GFP_KERNEL);
	if (!m)
		return -ENOMEM;
	m->dev = dev;

	ret = of_property_read_u32(dev->of_node, "reg", &m->base);
	if (ret)
		return dev_err_probe(dev, ret, "no reg property\n");

	/* The parent SPMI device owns the PMIC regmap, as clk-spmi-pmic-div
	 * also does. Nothing here creates a second one.
	 */
	m->regmap = dev_get_regmap(dev->parent, NULL);
	/* Runtime OF population cannot find an SPMI parent through the
	 * platform-only lookup, and may attach this child to platform_bus.
	 * Resolve the actual PMIC on its own bus; never create a new regmap.
	 */
	if (!m->regmap) {
		pmic = spmi_find_device_by_of_node(dev->of_node->parent);
		if (!pmic)
			return -EPROBE_DEFER;
		m->regmap = dev_get_regmap(&pmic->dev, NULL);
		put_device(&pmic->dev);
	}
	if (!m->regmap)
		return dev_err_probe(dev, -EINVAL,
				     "no regmap on the parent PMIC\n");

	m->pinctrl = devm_pinctrl_get(dev);
	if (IS_ERR(m->pinctrl))
		return dev_err_probe(dev, PTR_ERR(m->pinctrl),
				     "no pinctrl\n");
	m->state_off = pinctrl_lookup_state(m->pinctrl, "default");
	if (IS_ERR(m->state_off))
		m->state_off = NULL;
	m->state_divclk = pinctrl_lookup_state(m->pinctrl, "divclk");
	if (IS_ERR(m->state_divclk))
		m->state_divclk = NULL;

	platform_set_drvdata(pdev, m);

	ret = lumia_read(m, m->base + LUMIA_DIV_CTL1, &val);
	if (ret)
		return dev_err_probe(dev, ret, "cannot read DIV_CTL1\n");

	/*
	 * Nothing is programmed at probe. The experiment is driven from sysfs
	 * so the evidence file records the transition rather than inheriting a
	 * state that was already there when it started looking.
	 */
	dev_info(dev,
		 "Lumia MCLK experiment ready: base 0x%04x, DIV_CTL1 %02x, divclk state %s\n",
		 m->base, val & 0xff, m->state_divclk ? "present" : "MISSING");
	return 0;
}

static const struct of_device_id lumia_mclk_of_match[] = {
	{ .compatible = "lumia,rm940-mclk-div-experiment" },
	{ }
};
MODULE_DEVICE_TABLE(of, lumia_mclk_of_match);

static struct platform_driver lumia_mclk_driver = {
	.driver = {
		.name = "lumia-mclk-experiment",
		.of_match_table = lumia_mclk_of_match,
		.dev_groups = lumia_mclk_groups,
	},
	.probe = lumia_mclk_probe,
};

int lumia_mclk_experiment_register(void)
{
	return platform_driver_register(&lumia_mclk_driver);
}

void lumia_mclk_experiment_unregister(void)
{
	platform_driver_unregister(&lumia_mclk_driver);
}
