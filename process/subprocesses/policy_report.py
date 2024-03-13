"""Analysis report subprocess for policy checklist formatting and reporting."""

import os

import pandas as pd
from fpdf import FPDF


def get_policy_checklist(xlsx) -> dict:
    """Get and format policy checklist from Excel into series of DataFrames organised by indicator and measure in a dictionary."""
    from subprocesses.ghsci import policies

    try:
        df = pd.read_excel(
            xlsx, sheet_name='Policy Checklist', header=1, usecols='A:N',
        )
        df.columns = [
            'Indicators',
            'Measures',
            'Principles',
            'Policy',
            'Level of government',
            'Adoption date',
            'Citation',
            'Text',
            'Mandatory',
            'Measurable target',
            'Measurable target text',
            'Evidence-informed threshold',
            'Threshold explanation',
            'Notes',
        ]
        # Strip redundant white space (e.g. at start or end of cell values that could impede matching or formatting)
        df = df.apply(lambda x: x.str.strip() if x.dtype == 'object' else x)
        # Exclude dataframe rows where an indicator is defined without a corresponding measure
        # These are short name headings, and this is the quickest way to get rid of them!
        df = df.query('~(Indicators == Indicators and Measures != Measures)')
        # Remove the 'Public Open Space Policies' section that is nested within the Walkability section; it doesn't work well with the current formatting
        df = df.query('~(Measures=="PUBLIC OPEN SPACE POLICIES")')
        # fill down Indicators column values
        df.loc[:, 'Indicators'] = df.loc[:, 'Indicators'].ffill()
        # Only keep measures associated with indicators, replacing 'see also' reference indicators with NA
        df.loc[:, 'Measures'] = df.apply(
            lambda x: x['Measures']
            if x['Indicators'] in policies['Indicators'].keys()
            and x['Measures'] in policies['Indicators'][x['Indicators']]
            else pd.NA,
            axis=1,
        )
        # fill down Measures column values
        df.loc[:, 'Measures'] = df.loc[:, 'Measures'].ffill()
        df = df.loc[~df['Indicators'].isna()]
        df = df.loc[df['Indicators'] != 'Indicators']
        df['qualifier'] = (
            df['Principles']
            .apply(
                lambda x: x.strip()
                if (
                    str(x).strip() == 'No'
                    or str(x).strip() == 'Yes'
                    or str(x).strip() == 'Yes, explicit mention of:'
                )
                else pd.NA,
            )
            .ffill()
            .fillna('')
        )
        # replace df['qualifier'] with '' where df['Principles'] is in ['Yes','No'] (i.e. where df['Principles'] is a qualifier)
        df = df.loc[
            ~df['Principles'].isin(
                ['', 'No', 'Yes', 'Yes, explicit mention of:'],
            )
        ]
        # Remove measures ending in … (signifies that options are avilable in the subsequent rows)
        df = df.query('~(Measures.str.endswith("…"))')
        # df.loc[:, 'Principles'] = df.apply(
        #     lambda x: x['Principles']
        #     if x['qualifier'] == ''
        #     else f"{x['qualifier']}: {x['Principles']}".replace('::', ':'),
        #     axis=1,
        # )
        # df.drop(columns=['qualifier'], inplace=True)
        return df
    except Exception as e:
        print(
            f'Error reading policy checklist; please ensure these have been completed.  Specific error: {e}',
        )
        return None


def get_policy_setting(xlsx) -> dict:
    """Get and format policy checklist from Excel into series of DataFrames organised by indicator and measure in a dictionary."""
    try:
        df = pd.read_excel(xlsx, sheet_name='Collection details', header=3)
        if len(df.columns) < 3:
            print(
                'Policy checklist collection details appear not to have completed (no values found in column C); please check the specified file has been completed.',
            )
            return None
        df.columns = ['item', 'location', 'value']
        df.loc[:, 'item'] = df.loc[:, 'item'].ffill()
        setting = {}
        setting['Person(s)'] = df.loc[
            df['item'] == 'Name of person(s) completing checklist:', 'value',
        ].values[0]
        setting['E-mail'] = df.loc[
            df['item'] == 'Email address(es):', 'value',
        ].values[0]
        setting['Date'] = df.loc[
            df['item'] == 'Date completed', 'value',
        ].values[0]
        setting['City'] = df.loc[df['location'] == 'City', 'value'].values[0]
        setting['Region'] = df.loc[df['location'] == 'Region', 'value'].values[
            0
        ]
        setting['Country'] = df.loc[
            df['location'] == 'Country', 'value',
        ].values[0]
        setting['Levels of Government'] = (
            df.loc[
                (
                    df['item']
                    == 'Names of level(s) of government policy included the policy checklist'
                )
            ]
            .dropna()
            .iloc[:, 1:]
            .copy()
        )
        setting['Levels of Government'] = '\n'.join(
            setting['Levels of Government']
            .apply(lambda x: f'{x.location}: {x.value}', axis=1)
            .values,
        )
        setting['Environmental disaster context'] = {}
        disasters = [
            'Severe storms ',
            'Floods',
            'Bushfires/wildfires',
            'Heatwaves',
            'Extreme cold',
            'Typhoons',
            'Hurricanes',
            'Cyclones',
            'Earthquakes',
        ]
        for disaster in disasters:
            setting['Environmental disaster context'][disaster] = df.loc[
                (df['item'] == disaster)
                & (df['location'] != 'Other (please specify)'),
                'value',
            ].values[0]
        setting['Environmental disaster context']['Other'] = df.loc[
            df['location'] == 'Other (please specify)', 'value',
        ].values[0]
        setting['Environmental disaster context'] = '\n'.join(
            [
                f'{x}: {setting["Environmental disaster context"][x]}'
                for x in setting['Environmental disaster context']
                if str(setting['Environmental disaster context'][x]) != 'nan'
            ],
        )
        for x in setting:
            if setting[x] == '':
                setting[x] = 'Not specified'
        return setting
    except Exception as e:
        print(
            f'Error reading policy checklist "Collection details" worksheet; please ensure that this has been completed.\nSpecific error: {e}',
        )
        return None


# PDF layout set up
class PDF_Policy_Report(FPDF):
    """PDF report class for analysis report."""

    def __init__(self, policy_checklist, *args, **kwargs):
        from subprocesses._utils import prepare_pdf_fonts

        super(self.__class__, self).__init__(*args, **kwargs)
        self.file = policy_checklist
        self.setting = get_policy_setting(self.file)
        self.checklist = get_policy_checklist(self.file)
        self.location = f'{self.setting["City"]}, {self.setting["Country"]}'
        prepare_pdf_fonts(
            self,
            report_configuration='configuration/_report_configuration.xlsx',
            report_language='English',
        )

    def render_toc(self, outline):
        """Render table of contents."""
        self.x = self.l_margin
        self.set_font(style='', size=12)
        for section in outline:
            self.ln()
            self.cell(txt=section.name)

    def header(self):
        """Header of the report."""
        self.set_margins(19, 20, 19)
        if self.page_no() == 1:
            # Rendering logo:
            self.image(
                'configuration/assets/GOHSC - white logo transparent.svg',
                19,
                19,
                42,
            )
            # Printing title:
            self.set_font('helvetica', 'B', 24)
            with self.local_context(text_color=(89, 39, 226)):
                self.write_html(
                    f'<br><br><section><h1><font color="#5927E2"><b>{self.location}</b></font></h1></section>',
                )
                self.write_html(
                    '<font color="#CCCCCC"><b>Policy report</b></font><br><br>',
                )
        else:
            # Rendering logo:
            self.image(
                'configuration/assets/GOHSC - white logo transparent.svg',
                19,
                19,
                42,
            )
            # Printing title:
            self.set_font('helvetica', 'B', 18)
            with self.local_context(text_color=(89, 39, 226)):
                self.set_x(38)
                self.multi_cell(
                    w=134, txt=self.location, border=0, align='R',
                )
                self.set_x(0)
        self.set_margins(19, 32, 19)

    def footer(self):
        """Page footer function."""
        # Position cursor at 1.5 cm from bottom:
        self.set_y(-15)
        # Setting font: helvetica italic 8
        self.set_font('helvetica', 'I', 8)
        # Printing page number:
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')

    def format_policy_checklist(self, df) -> None:
        """Format policy checklist into report."""
        from subprocesses.ghsci import policies

        sections = {
            'CITY PLANNING REQUIREMENTS': {
                'indicators': {
                    'Integrated transport and urban planning': 'Integrated transport and urban planning actions to create healthy and sustainable cities',
                    'Air pollution': 'Limit air pollution from land use and transport',
                    'Transport infrastructure investment by mode': 'Priority investment in public and active transport',
                    'Disaster mitigation': 'City planning contributes to adaptation and mitigating  the effects of climate change',
                },
            },
            'WALKABILITY AND OPEN SPACE POLICIES': {
                'indicators': {
                    'Density': 'Appropriate context-specific housing densities that encourage walking; including higher density development around activity centres and transport hubs',
                    'Demand management': 'Limit car parking and price parking appropriately for context',
                    'Diversity': 'Diverse mix of housing types and local destinations needed for daily living',
                    'Destination proximity': ' Local destinations for walkable cities',
                    'Desirability': 'Crime prevention through urban design principles, manage traffic exposure, and establish urban greening provisions',
                    'Design': 'Create pedestrian- and cycling-friendly neighbourhoods, requiring highly connected street networks; pedestrian and cycling infrastructure provision; and public open space',
                },
            },
            'PUBLIC TRANSPORT POLICIES': {
                'indicators': {
                    'Destination accessibility': 'Coordinated planning for transport, employment and infrastructure that ensures access by public transport',
                    'Distribution of employment': 'A balanced ratio of jobs to housing ',
                    'Distance to public transport': 'Nearby, walkable access to public transport',
                },
            },
        }
        report = {}
        for section in sections:
            report[section] = {}
            self.add_page()
            self.write_html(
                f'<section><h1><font color="#5927E2">{section}</font></h1><br></section>',
            )
            for indicator in sections[section]['indicators']:
                # clean up Measures column values (remove 'see also' references, remove leading and trailing spaces, replace '&nbsp' with ' ', replace '  ' with ' ')
                df.loc[
                    df.loc[:, 'Indicators']
                    == sections[section]['indicators'][indicator],
                    'Measures',
                ] = (
                    df.loc[
                        df.loc[:, 'Indicators']
                        == sections[section]['indicators'][indicator]
                    ]
                    .apply(
                        lambda x: x.str.strip()
                        .replace('&nbsp', ' ')
                        .replace('  ', '')
                        if x['Measures']
                        in policies['Indicators'][x['Indicators']]
                        else pd.NA,
                        axis=1,
                    )['Measures']
                    .ffill()
                )
                measures = df.loc[
                    df.loc[:, 'Indicators']
                    == sections[section]['indicators'][indicator],
                    'Measures',
                ].unique()
                ind = f"{indicator} - {sections[section]['indicators'][indicator]}"
                report[section][ind] = {}
                self.write_html(
                    f'<section><h2><font color="#5927E2">{ind}</font></h2><br></section>',
                )
                for measure in measures:
                    qualifiers = df.loc[
                        (
                            df.loc[:, 'Indicators']
                            == sections[section]['indicators'][indicator]
                        )
                        & (df.loc[:, 'Measures'] == measure),
                        'qualifier',
                    ].unique()
                    report[section][ind][measure] = {}
                    self.write_html(
                        f'<section><h3><font color="#5927E2">{measure}</font></h3><br></section>',
                    )
                    for qualifier in qualifiers:
                        if qualifier == '':
                            subtable = (
                                df.loc[
                                    (
                                        df.loc[:, 'Indicators']
                                        == sections[section]['indicators'][
                                            indicator
                                        ]
                                    )
                                    & (df.loc[:, 'Measures'] == measure)
                                    & (df.loc[:, 'qualifier'] == qualifier),
                                    df.columns[3:-1],
                                ]
                                .transpose()
                                .unstack()
                                .reset_index()[['level_1', 0]]
                                # .transpose()
                                # .reset_index()
                            )
                            subtable.columns = ['criteria', 'value']
                            # print(f"{section} - {ind} - {measure}")
                            # print(subtable)
                            if (
                                not (subtable)
                                .query('criteria=="Policy"')['value']
                                .isna()[0]
                            ):
                                report[section][ind][
                                    measure
                                ] = subtable.dropna()
                                if len(report[section][ind][measure]) > 0:
                                    self.format_criteria(
                                        report[section][ind][measure],
                                    )
                        else:
                            report[section][ind][measure][qualifier] = {}
                            self.write_html(
                                f'<section><h4><font color="#5927E2">{qualifier}</font></h4><br></section>',
                            )
                            principles = df.loc[
                                (
                                    df.loc[:, 'Indicators']
                                    == sections[section]['indicators'][
                                        indicator
                                    ]
                                )
                                & (df.loc[:, 'Measures'] == measure)
                                & (df.loc[:, 'qualifier'] == qualifier),
                                'Principles',
                            ].unique()
                            for principle in principles:
                                subtable = (
                                    df.loc[
                                        (
                                            df.loc[:, 'Indicators']
                                            == sections[section]['indicators'][
                                                indicator
                                            ]
                                        )
                                        & (df.loc[:, 'Measures'] == measure)
                                        & (df.loc[:, 'qualifier'] == qualifier)
                                        & (
                                            df.loc[:, 'Principles']
                                            == principle
                                        ),
                                        df.columns[3:-1],
                                    ]
                                    .transpose()
                                    .unstack()
                                    .reset_index()[['level_1', 0]]
                                    # .transpose()
                                    # .reset_index()
                                )
                                subtable.columns = ['criteria', 'value']
                                # print(f"{section} - {ind} - {measure} - {qualifier} - {principle}")
                                # print(subtable)
                                if (
                                    not (subtable)
                                    .query('criteria=="Policy"')['value']
                                    .isna()[0]
                                ):
                                    self.write_html(
                                        f'<section><h5><font color="#5927E2">{principle}</font></h5><br></section>',
                                    )
                                    align = 'CENTER'
                                    report[section][ind][measure][qualifier][
                                        principle
                                    ] = subtable.dropna()
                                    if (
                                        len(
                                            report[section][ind][measure][
                                                qualifier
                                            ][principle],
                                        )
                                        > 0
                                    ):
                                        self.format_criteria(
                                            report[section][ind][measure][
                                                qualifier
                                            ][principle],
                                        )

    def format_criteria(self, subtable: pd.DataFrame) -> None:
        """Format criteria into report."""
        with self.table(
            borders_layout='HORIZONTAL_LINES',
            # borders_layout='SINGLE_TOP_LINE',
            # cell_fill_color=200,  # greyscale
            # cell_fill_mode='ROWS',
            text_align=('LEFT', 'LEFT'),
            line_height=5,
            col_widths=(40, 60),
            first_row_as_headings=False,
        ) as table:
            # add header row
            # capture = table.row(list(subtable.columns))
            # add data rows
            for d in subtable.itertuples():
                row = table.row()
                for datum in d[1:]:
                    capture = row.cell(str(datum))

    def generate_policy_report(self):
        """Generate analysis report."""
        print('Generating policy report (this may take some time)...')
        self.add_page()
        self.set_font('Dejavu', size=12)
        # self.insert_toc_placeholder(self.render_toc)
        # self.write_html('<toc></toc>')
        collection_details = (
            pd.DataFrame.from_dict(self.setting, orient='index')
            .reset_index()
            .dropna()
        )
        self.format_criteria(collection_details)
        self.format_policy_checklist(self.checklist)
        report_file = f'{self.file.replace(".xlsx",".pdf")}'
        self.output(report_file)
        print(f'Report saved to {report_file}')
        return report_file
