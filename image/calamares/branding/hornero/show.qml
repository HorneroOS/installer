// HorneroOS installation slideshow (Calamares slideshowAPI 2) on Hornero
// Signal (RFC 0001 + amendment 3, Signal Visual Language "Signal Bezel").

// Tells the OS-family story while files are copied: Desktop, Studio and
// Gaming, each with the packages its installer choice really adds (from
// image/calamares/modules/compositions.json) and its real maturity
// (Preview). No screenshots: these are typographic instrument cards, so
// nothing here can show a look the installed release does not have.
// Colours are Signal Night roles; fonts come from ttf-ibm-plex on the
// live medium, with fontconfig fallbacks.
import QtQuick
import calamares.slideshow 1.0

Presentation {
    id: presentation

    // Signal Night roles used by the slideshow (RFC 0001 §3.2, amendment 3).
    readonly property color ground: "#0C1016"
    readonly property color sunken: "#10151C"
    readonly property color panel: "#1B2430"
    readonly property color ink: "#E6EBF1"
    readonly property color inkMuted: "#A9B7C6"
    readonly property color rule: "#2D3B4B"
    readonly property color ruleStrong: "#8393A6"
    readonly property color signal: "#F2AC52"
    // onSignal role (named so QML does not read it as a signal handler).
    readonly property color inkOnSignal: "#1E1304"
    readonly property string sans: "IBM Plex Sans"
    readonly property string mono: "IBM Plex Mono"
    readonly property string display: "IBM Plex Sans Condensed"
    property bool reducedMotion: false

    function nextSlide() {
        presentation.goToNextSlide();
    }

    // Calamares API 2: called when the installation page is shown/left.
    function onActivate() {
        presentation.currentSlide = 0;
        advanceTimer.restart();
    }

    function onLeave() {
        advanceTimer.stop();
    }

    Timer {
        id: advanceTimer

        interval: 12000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.nextSlide()
    }

    Rectangle {
        anchors.fill: parent
        z: -1
        color: presentation.ground
    }

    Slide {
        Card {
            channel: "00 · INSTALLING"
            numeral: "00"
            title: "HorneroOS is being installed"
            body: "The base system is being copied first, then the edition you chose. This takes a while; keep the computer powered on. When it finishes, restart and remove the installation medium."
        }

    }

    Slide {
        Card {
            channel: "01 · DESKTOP"
            numeral: "01"
            title: "HorneroOS Desktop"
            chip: "SUPPORTED"
            body: "A Wayland-first desktop on Hyprland with Hornero Shell: bars, launcher, notifications, layouts and the Control Center. Studio and Gaming build on it. Niri is offered as an experimental compositor."
            contentsLabel: "CORE"
            contents: ["hyprland", "hornero-shell", "hornero-config", "horneroctl-bin", "hornero-greeter"]
        }

    }

    Slide {
        Card {
            channel: "02 · STUDIO"
            numeral: "02"
            title: "HorneroOS Studio"
            chip: "SUPPORTED"
            body: "A creative workstation based on Desktop: low-latency audio routing through PipeWire's JACK layer, plus applications for music, illustration, 3D, video editing and streaming."
            contentsLabel: "ADDS TO DESKTOP"
            contents: ["pipewire-jack", "qpwgraph", "ardour", "guitarix", "krita", "blender", "kdenlive", "obs-studio", "ffmpeg"]
        }

    }

    Slide {
        Card {
            channel: "03 · GAMING"
            numeral: "03"
            title: "HorneroOS Gaming"
            chip: "SUPPORTED"
            body: "A gaming desktop based on Desktop with Gamescope, GameMode and MangoHud ready. Game launchers are explicit opt-ins: none is installed unless you add it."
            contentsLabel: "ADDS TO DESKTOP"
            contents: ["gamescope", "gamemode", "mangohud", "vulkan-icd-loader", "vulkan-tools", "steam-devices", "xorg-xwayland"]
        }

    }

    Slide {
        Card {
            channel: "04 · AFTER FIRST BOOT"
            numeral: "04"
            title: "Make it yours"
            body: "Change bars, layouts and themes in the Control Center, or from a terminal with horneroctl. Report problems at github.com/HorneroOS/installer/issues so the next preview is better."
        }

    }

    component Eyebrow: Text {
        color: presentation.inkMuted
        font.family: presentation.mono
        font.pixelSize: 12
        font.letterSpacing: 1
    }

    component Card: Item {
        id: card

        property string channel: ""
        property string title: ""
        property string body: ""
        property string chip: ""
        property var contents: []
        property string contentsLabel: "INSTALLS"
        property string numeral: ""

        anchors.fill: parent
        anchors.margins: 40

        // Channel numeral: large Plex Sans Condensed Light in ruleStrong,
        // the instrument's channel plate.
        Text {
            id: plate

            anchors.verticalCenter: body.verticalCenter
            text: card.numeral
            color: presentation.ruleStrong
            font.family: presentation.display
            font.weight: Font.Light
            font.pixelSize: 120
            font.features: {
                "tnum": 1
            }
        }

        Rectangle {
            id: plateRule

            anchors.left: plate.right
            anchors.leftMargin: 28
            anchors.verticalCenter: body.verticalCenter
            width: 1
            height: body.height
            color: presentation.rule
        }

        // La Plata 45° diagonal: brand surface only, top-right corner.
        Item {
            anchors.right: parent.right
            anchors.top: parent.top
            width: 72
            height: 8
            clip: true

            Repeater {
                model: 14

                Rectangle {
                    required property int index

                    x: index * 6 - 8
                    y: -20
                    width: 1.5
                    height: 48
                    rotation: 45
                    antialiasing: true
                    color: presentation.signal
                    opacity: 0.85
                }

            }

        }

        Item {
            id: body

            anchors.left: plateRule.right
            anchors.leftMargin: 28
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            height: head.height + (well.visible ? well.height + 20 : 0)

            Column {
                id: head

                width: parent.width - 96
                spacing: 10

                Eyebrow {
                    text: card.channel
                }

                Row {
                    spacing: 14

                    Text {
                        text: card.title
                        color: presentation.ink
                        font.family: presentation.display
                        font.weight: Font.Medium
                        font.pixelSize: 34
                    }

                    Rectangle {
                        // On-air chip: the edition's real maturity.
                        anchors.verticalCenter: parent.verticalCenter
                        visible: card.chip !== ""
                        width: chipText.implicitWidth + 16
                        height: chipText.implicitHeight + 6
                        radius: 3
                        color: presentation.signal

                        Text {
                            id: chipText

                            anchors.centerIn: parent
                            text: card.chip
                            color: presentation.inkOnSignal
                            font.family: presentation.mono
                            font.weight: Font.DemiBold
                            font.pixelSize: 11
                            font.letterSpacing: 1
                        }

                    }

                }

                Rectangle {
                    width: parent.width
                    height: 1
                    color: presentation.rule
                }

                Text {
                    width: parent.width
                    text: card.body
                    wrapMode: Text.WordWrap
                    color: presentation.ink
                    font.family: presentation.sans
                    font.pixelSize: 15
                    lineHeight: 1.3
                }

            }

            // Readout well listing what the choice really adds.
            Rectangle {
                id: well

                visible: card.contents.length > 0
                anchors.top: head.bottom
                anchors.topMargin: 20
                width: parent.width
                height: wellColumn.implicitHeight + 24
                radius: 3
                color: presentation.sunken
                border.width: 1
                border.color: presentation.rule

                Column {
                    id: wellColumn

                    x: 14
                    y: 12
                    width: parent.width - 28
                    spacing: 8

                    Eyebrow {
                        text: card.contentsLabel
                    }

                    Flow {
                        width: parent.width
                        spacing: 8

                        Repeater {
                            model: card.contents

                            Rectangle {
                                required property string modelData

                                width: pkg.implicitWidth + 14
                                height: pkg.implicitHeight + 8
                                radius: 3
                                color: "transparent"
                                border.width: 1
                                border.color: presentation.ruleStrong

                                Text {
                                    id: pkg

                                    anchors.centerIn: parent
                                    text: parent.modelData
                                    color: presentation.ink
                                    font.family: presentation.mono
                                    font.pixelSize: 12
                                }

                            }

                        }

                    }

                }

            }

        }

    }

}
